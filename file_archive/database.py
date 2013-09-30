import sqlite3

from .errors import Error, CreationError, InvalidStore


class MetadataStore(object):
    """The database holding metadata associated to SHA1 hashs.
    """
    _TYPES = [('TEXT', 'str'), ('INTEGER', 'int')]

    def __init__(self, database):
        try:
            self.conn = sqlite3.connect(database)
            self.conn.row_factory = sqlite3.Row
            cur = self.conn.cursor()
            tables = cur.execute(u'''
                    SELECT name FROM sqlite_master WHERE type = 'table'
                    ''')
            if set(r['name'] for r in tables.fetchall()) != set([u'metadata']):
                raise InvalidStore("Database doesn't have required structure")
        except sqlite3.Error, e:
            raise InvalidStore("Cannot access database: %s: %s" % (
                    e.__class__.__name__, e.message))

    @staticmethod
    def create_db(database):
        try:
            conn = sqlite3.connect(database)
            query = u'''
                    CREATE TABLE metadata(
                        hash VARCHAR(40) NOT NULL,
                        mkey VARCHAR(255) NULL
                    '''
            indexes = [
                    u'CREATE INDEX hash_idx ON metadata(hash)',
                    u'CREATE INDEX mkey_idx ON metadata(mkey)']

            for datatype, name in MetadataStore._TYPES:
                query += u'''
                        , mvalue_{name} {type} NULL
                        '''.format(name=name, type=datatype)
                indexes.append(u'''
                        CREATE INDEX mvalue_{name} ON metadata(mvalue_{name})
                        '''.format(name=name))
            query += u')'

            cur = conn.cursor()
            cur.execute(query)
            for idx_query in indexes:
                cur.execute(idx_query)

            conn.commit()
            conn.close()
        except sqlite3.Error, e: # pragma: no cover
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
                    SELECT hash FROM metadata
                    WHERE hash = :hash
                    LIMIT 1
                    ''',
                    {'hash': key})
            if cur.fetchone() is not None:
                raise KeyError("Already have metadata for hash")
            if not metadata:
                cur.execute(u'''
                        INSERT INTO metadata(hash) VALUES(:hash)
                        ''',
                        {'hash': key})
            else:
                for mkey, mvalue in metadata.iteritems():
                    if isinstance(mvalue, basestring):
                        t = 'str'
                    elif isinstance(mvalue, (int, long)):
                        t = 'int'
                    elif isinstance(mvalue, dict):
                        r = dict(mvalue)
                        t = r.pop('type')
                        mvalue = r.pop('value')
                    else:
                        raise TypeError(
                                "Metadata values should be dictionaries with "
                                "the format:\n"
                                "{'type': 'int/str/...', 'value': <value>}")
                    cur.execute(u'''
                            INSERT INTO metadata(hash, mkey, mvalue_{name})
                            VALUES(:hash, :key, :value)
                            '''.format(name=t, hash=mkey, value=mvalue),
                            {'hash': key, 'key': mkey, 'value': mvalue})
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
                    DELETE FROM metadata WHERE hash = :hash
                    ''',
                    {'hash': key})
            if not cur.rowcount:
                raise KeyError(key)
            self.conn.commit()
        except:
            self.conn.rollback()
            raise

    def get(self, key):
        """Gets a row from the hash.
        """
        cur = self.conn.cursor()
        rows = cur.execute(u'''
                SELECT * FROM metadata
                WHERE hash = :hash
                ''',
                {'hash': key})
        result = ResultBuilder(rows)
        try:
            return next(result)
        except StopIteration:
            raise KeyError("No metadata for hash")

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
        # Build the LIMIT part from the limit arg (number or None)
        if limit is not None:
            limit = u'LIMIT %d' % limit
        else:
            limit = u''

        cur = self.conn.cursor()
        if not conditions:
            hquery = u'''
                    SELECT DISTINCT hash
                    FROM metadata
                    {limit}
                    '''.format(limit=limit)
            params = {}
        else:
            conditems = self._make_conditions(conditions)
            i, key, cond0, params = next(conditems)
            hquery = u'''
                    SELECT i0.hash
                    FROM metadata i0
                    '''
            params['key0'] = key
            for i, key, cond, prms in conditems:
                hquery += u'''
                        INNER JOIN metadata i{i} ON i0.hash = i{i}.hash
                            AND i{i}.mkey = :key{i} AND {cond}
                        '''.format(i=i, cond=cond)
                params['key%d' % (i)] = key
                params.update(prms)
            hquery += u'''
                    WHERE i0.mkey = :key0 AND {cond}
                    {limit}
                    '''.format(cond=cond0, limit=limit)

        # And we put that in the query
        rows = cur.execute(u'''
                SELECT *
                FROM metadata
                WHERE hash IN ({hashes})
                ORDER BY hash
                '''.format(hashes=hquery),
                params)

        return ResultBuilder(rows)

    def _make_conditions(self, conditions):
        for i, (key, value) in enumerate(conditions.iteritems()):
            if isinstance(value, basestring):
                t = 'str'
                req = [('equal', value)]
            elif isinstance(value, (int, long)):
                t = 'int'
                req = [('equal', value)]
            elif isinstance(value, dict):
                req = dict(value)
                try:
                    t = req.pop('type')
                except KeyError:
                    raise TypeError("Query conditions should include key "
                                     "'type'")
                req = req.iteritems()
                if t not in ('str', 'int'):
                    raise TypeError("Unknown data type %r" % t)
            else:
                raise TypeError(
                        "Query conditions should be dictionaries with the "
                        "format:\n"
                        "{'type': 'int/str/...', <condition>}")

            var = 'i{i}.mvalue_{t}'.format(i=i, t=t)
            conds = []
            params = {}
            for j, (k, v) in enumerate(req):
                val = ':val{i}_{j}'.format(i=i, j=j)
                params['val%d_%d' % (i, j)] = v
                if k == 'equal':
                    conds.append('{var} = {val}'.format(var=var, val=val))
                elif t == 'int' and k == 'lt':
                    conds.append('{var} < {val}'.format(var=var, val=val))
                elif t == 'int' and k == 'gt':
                    conds.append('{var} > {val}'.format(var=var, val=val))
                else:
                    raise ValueError("Unsupported operation %r" % k)
            yield (i,
                   key,
                   ' AND '.join(conds),
                   params)


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

    def __iter__(self): # pragma: no cover
        return self

    def next(self):
        if self.rows is None:
            raise StopIteration
        if self.record is None:
            r = next(self.rows) # Might raise StopIteration
        else:
            r = self.record
        h = r['hash']
        def get_value(r):
            for datatype, name in MetadataStore._TYPES:
                v = r['mvalue_%s' % name]
                if v is not None:
                    return v
            else: # pragma: no cover
                raise Error("SQL query didn't return a value for "
                            "hash=%s, key=%s" % (r['hash'], r['mkey']))
        # We are outer joining, so a hash with no metadata will be returned as
        # a single row with mkey=NULL and everything but hash NULL
        if len(r) > 1 and r['mkey']:
            dct = {'hash': h, r['mkey']: get_value(r)}
        else:
            dct = {'hash': h}

        for r in self.rows:
            if r['hash'] != h:
                self.record = r
                return dct
            dct[r['mkey']] = get_value(r)
        else:
            self.rows = None
        return dct
