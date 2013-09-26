import sqlite3

from .errors import CreationError, InvalidStore


class MetadataStore(object):
    """The database holding metadata associated to SHA1 hashs.
    """
    def __init__(self, database):
        try:
            self.conn = sqlite3.connect(database)
            self.conn.row_factory = sqlite3.Row
            cur = self.conn.cursor()
            tables = cur.execute(u'''
                    SELECT name FROM sqlite_master WHERE type = 'table'
                    ''')
            if set(r['name'] for r in tables.fetchall()) != set([
                    u'hashes', u'metadata_str', u'metadata_int']):
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

            for datatype, name in [('TEXT', 'str'), ('INTEGER', 'int')]:
                conn.execute(u'''
                        CREATE TABLE metadata_{n}(
                            hash VARCHAR(40),
                            mkey VARCHAR(255),
                            mvalue {t})
                        '''.format(n=name, t=datatype))
                conn.execute(u'''
                        CREATE INDEX hash_{n}_idx ON metadata_{n}(hash)
                        '''.format(n=name))
                conn.execute(u'''
                        CREATE INDEX mkey_{n}_idx ON metadata_{n}(mkey)
                        '''.format(n=name))
                conn.execute(u'''
                        CREATE INDEX mvalue_{n}_idx ON metadata_{n}(mvalue)
                        '''.format(n=name))
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
                    INSERT INTO metadata_str(hash, mkey, mvalue)
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
                    DELETE FROM metadata_str WHERE hash = :hash
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
        if limit is not None:
            limit = u'LIMIT %d' % limit
        else:
            limit = u''
        cur = self.conn.cursor()
        if not conditions:
            rows = cur.execute(u'''
                    SELECT hashes.hash, metadata_str.mkey, metadata_str.mvalue
                    FROM hashes
                    LEFT OUTER JOIN metadata_str
                            ON hashes.hash = metadata_str.hash
                    ORDER BY hashes.hash
                    {limit}
                    '''.format(limit=limit))
        else:
            conditems = conditions.iteritems()
            meta_key, meta_value = next(conditems)
            query = u'''
                    SELECT i0.hash
                    FROM metadata_str i0
                    '''
            cond0, params = self._make_condition(0, meta_key, meta_value)
            params['key0'] = meta_key
            for j, (meta_key, meta_value) in enumerate(conditems):
                cond, prms = self._make_condition(j+1, meta_key, meta_value)
                query += u'''
                        INNER JOIN metadata_str i{i} ON i0.hash = i{i}.hash
                            AND i{i}.mkey = :key{i} AND {cond}
                        '''.format(i=j+1, cond=cond)
                params['key%d' % (j+1)] = meta_key
                params.update(prms)
            query += u'''
                    WHERE i0.mkey = :key0 AND {cond}
                    {limit}
                    '''.format(cond=cond0, limit=limit)
            rows = cur.execute(u'''
                    SELECT hash, mkey, mvalue FROM metadata_str
                    WHERE hash IN ({hashes})
                    ORDER BY hash
                    '''.format(hashes=query),
                    params)

        return ResultBuilder(rows)

    def _make_condition(self, i, key, value):
        return ('i{i}.mvalue = :val{i}'.format(i=i),
                {'val%d' % i: value})


class ResultBuilder(object):
    """This regroups rows for key-values of a single hash into one dict.

    Example:
    +------+------+--------+
    | hash | mkey | mvalue |        [
    +------+------+--------+         {'hash': 'aaaa', 'one': 11, 'two': 12},
    | aaaa | one  |   11   |   =>    {'hash': 'bbbb', 'one': 21, 'six': 26},
    | aaaa | two  |   12   |        ]
    | bbbb | one  |   21   |
    | bbbb | six  |   26   |
    +------+------+--------+
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
            r = next(self.rows) # Might raise StopIteration
        else:
            r = self.record
        h = r['hash']
        # We might be outer-joining hashes with metadata, in which case a hash
        # that is stored with no metadata will be returned as a single row
        # hash=hash mkey=NULL mvalue=NULL
        if len(r) == 3 and r['mkey']:
            dct = {'hash': h, r['mkey']: r['mvalue']}
        else:
            dct = {'hash': h}

        for r in self.rows:
            if r['hash'] != h:
                self.record = r
                return dct
            dct[r['mkey']] = r['mvalue']
        else:
            self.rows = None
        return dct
