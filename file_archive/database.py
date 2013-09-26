import sqlite3

from .errors import CreationError, InvalidStore


class MetadataStore(object):
    """The database holding metadata associated to SHA1 hashs.
    """
    def __init__(self, database):
        try:
            self.conn = sqlite3.connect(database)
            cur = self.conn.cursor()
            tables = cur.execute(u'''
                    SELECT name FROM sqlite_master WHERE type = 'table'
                    ''')
            if set(tables.fetchall()) != set([(u'metadata',), (u'hashes',)]):
                raise InvalidStore("Database doesn't have required structure")
        except sqlite3.Error, e:
            raise InvalidStore("Cannot access database: %s: %s" % (
                    e.__class__.__name__, e.message))

    @staticmethod
    def create_db(database):
        try:
            conn = sqlite3.connect(database)
            conn.execute(u'''
                    CREATE TABLE hashes(
                        hash VARCHAR(40))
                    ''')
            conn.execute(u'''
                    CREATE INDEX hashes_idx ON hashes(hash)
                    ''')

            conn.execute(u'''
                    CREATE TABLE metadata(
                        hash VARCHAR(40),
                        mkey VARCHAR(255),
                        mvalue VARCHAR(255))
                    ''')
            conn.execute(u'''
                    CREATE INDEX hash_idx ON metadata(hash)
                    ''')
            conn.execute(u'''
                    CREATE INDEX mkey_idx ON metadata(mkey)
                    ''')
            conn.execute(u'''
                    CREATE INDEX mvalue_idx ON metadata(mvalue)
                    ''')
            conn.commit()
            conn.close()
        except sqlite3.Error, e:
            raise CreationError("Could not create database: %s: %s" % (
                    e.__class__.__name__, e.message))

    def close(self):
        self.conn.commit()
        self.conn.close()

    def add(self, key, metadata):
        """Adds a hash and its metadata to the store.

        Raises KeyError if an entry already existed.
        """
        cur = self.conn.cursor()
        try:
            cur.execute(u'''
                    INSERT INTO hashes(hash)
                    VALUES(:hash)
                    ''',
                    {'hash': key})
            cur.executemany(u'''
                    INSERT INTO metadata(hash, mkey, mvalue)
                    VALUES(:hash, :key, :value)
                    ''',
                    ({'hash': key, 'key': k, 'value': v}
                     for k, v in metadata.iteritems()))
            self.conn.commit()
        except:
            self.conn.rollback()
            raise

    def remove(self, key):
        """Removes a hash and its metadata from the store.

        Raises KeyError if the entry didn't exist.
        """
        cur = self.conn.cursor()
        try:
            cur.execute(u'''
                    DELETE FROM hashes WHERE hash = :hash
                    ''',
                    {'hash': key})
            if cur.rowcount != 1:
                raise KeyError(key)
            cur.execute(u'''
                    DELETE FROM metadata WHERE hash = :hash
                    ''',
                    {'hash': key})
            self.conn.commit()
        except:
            self.conn.rollback()
            raise

    def query_one(self, conditions):
        """Returns at most one row matching the conditions, as a dict.

        The returned dict will have the 'hash' key plus all the stored
        metadata.

        conditions is a dictionary of metadata that need to be included in the
        actual dict of each hash.
        """
        rows = self.query_all(conditions, limit=1)
        try:
            return rows.next()
        except StopIteration:
            return None

    def query_all(self, conditions, limit=None):
        """Returns an iterable of rows matching the conditions.

        Each row is a dict, with at least the 'hash' key.
        """
        cur = self.conn.cursor()
        if not conditions:
            rows = cur.execute(u'''
                    SELECT hashes.hash, metadata.mkey, metadata.mvalue
                    FROM hashes
                    LEFT OUTER JOIN metadata ON hashes.hash=metadata.hash
                    ORDER BY hashes.hash
                    ''')
        else:
            conditems = conditions.iteritems()
            meta_key, meta_value = next(conditems)
            query = u'''
                    SELECT hash
                    FROM metadata i0
                    '''
            params = {'key0': meta_key, 'val0': meta_value}
            for j, (meta_key, meta_value) in enumerate(conditems):
                query += u'''
                        INNER JOIN metadata i{i} ON i0.hash = i{i}.hash
                            AND i{i}.mkey = :key{i} AND i{i}.mvalue = :val{i}
                        '''.format(i=j+1)
                params['key%d' % (j+1)] = meta_key
                params['val%d' % (j+1)] = meta_value
            query += u'''
                    WHERE i0.mkey = :key0 AND i0.mvalue = :val0
                    '''
            rows = cur.execute(u'''
                    SELECT hash, mkey, mvalue FROM metadata
                    WHERE hash IN ({hashes})
                    ORDER BY hash
                    '''.format(hashes=query),
                    params)

        return ResultBuilder(rows)


class ResultBuilder(object):
    """This regroups rows for key-values of a single hash into one dict.

    Example:
    +------+-----+-------+
    | hash | key | value |        [
    +------+-----+-------+         {'hash': 'aaaa', 'one': 11, 'two': 12},
    | aaaa | one |  11   |   =>    {'hash': 'bbbb', 'one': 21, 'six': 26},
    | aaaa | two |  12   |        ]
    | bbbb | one |  21   |
    | bbbb | six |  26   |
    +------+-----+-------+
    """
    def __init__(self, rows):
        self.rows = iter(rows)
        self.record = None

    def __iter__(self):
        return self

    def next(self):
        if self.rows is None:
            raise StopIteration
        if self.record is None:
            r = self.rows.next() # Might raise StopIteration
        else:
            r = self.record
        h = r[0]
        # We might be outer-joining hashes with metadata, in which case a hash
        # that is stored with no metadata will be returned as a single row
        # hash=hash mkey=NULL mvalue=NULL
        if len(r) == 3 and r[1]:
            dct = {'hash': h, r[1]: r[2]}
        else:
            dct = {'hash': h}

        for r in self.rows:
            if r[0] != h:
                self.record = r
                return dct
            dct[r[1]] = r[2]
        else:
            self.rows = None
        return dct
