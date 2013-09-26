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

            for datatype, name in MetadataStore._TYPES:
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
            # Builds a list of pairs for each value type
            pairs = {n: [] for t, n in self._TYPES}
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
                            "Metadata values should be dictionaries with the "
                            "format:\n"
                            "{'type': 'int/str/...', 'value': <value>}")
                pairs[t].append({'hash': key, 'key': mkey, 'value': mvalue})
            for t, n in self._TYPES:
                p = pairs[n]
                if not p:
                    continue
                cur.executemany(u'''
                        INSERT INTO metadata_{n}(hash, mkey, mvalue)
                        VALUES(:hash, :key, :value)
                        '''.format(n=n),
                        p)
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
            for t, n in self._TYPES:
                cur.execute(u'''
                        DELETE FROM metadata_{n} WHERE hash = :hash
                        '''.format(n=n),
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
        # Build the LIMIT part from the limit arg (number or None)
        if limit is not None:
            limit = u'LIMIT %d' % limit
        else:
            limit = u''

        # Build the SELECT field list and the OUTER JOIN for the metadata
        # tables
        n0 = self._TYPES[0][1]
        meta_select = u'''
                , metadata_{n0}.mkey AS mkey
                '''.format(n0=n0)
        meta_joins = u''
        for i, (t, n) in enumerate(self._TYPES):
            meta_select += u'''
                    , metadata_{n}.mvalue AS mvalue_{n}
                    '''.format(n=n)
            if i == 0:
                meta_joins += u'''
                        LEFT OUTER JOIN metadata_{n}
                        ON hashes.hash = metadata_{n}.hash
                        '''.format(n=n)
            else:
                meta_joins += u'''
                        LEFT OUTER JOIN metadata_{n}
                        ON hashes.hash = metadata_{n}.hash AND
                            metadata_{n}.mkey = metadata_{n0}.mkey
                        '''.format(n=n, n0=n0)

        cur = self.conn.cursor()
        if not conditions:
            # If we were not given any condition, we don't need a WHERE clause
            rows = cur.execute(u'''
                    SELECT hashes.hash
                    {meta_select}
                    FROM hashes
                    {meta_joins}
                    ORDER BY hashes.hash
                    '''.format(meta_select=meta_select,
                               meta_joins=meta_joins))
            # FIXME : limit is ignored here
        else:
            # Else, we need a WHERE clause with a subquery that requests the
            # hashes first
            conditems = conditions.iteritems()
            meta_key, meta_value = next(conditems)
            cond0, params, t = self._make_condition(0, meta_key, meta_value)
            hquery = u'''
                    SELECT i0.hash
                    FROM metadata_{t} i0
                    '''.format(t=t)
            params['key0'] = meta_key
            for j, (meta_key, meta_value) in enumerate(conditems):
                cond, prms, t = self._make_condition(j+1, meta_key, meta_value)
                hquery += u'''
                        INNER JOIN metadata_{t} i{i} ON i0.hash = i{i}.hash
                            AND i{i}.mkey = :key{i} AND {cond}
                        '''.format(i=j+1, t=t, cond=cond)
                params['key%d' % (j+1)] = meta_key
                params.update(prms)
            hquery += u'''
                    WHERE i0.mkey = :key0 AND {cond}
                    {limit}
                    '''.format(cond=cond0, limit=limit)

            # And we put that in the query
            rows = cur.execute(u'''
                    SELECT hashes.hash
                    {meta_select}
                    FROM hashes
                    {meta_joins}
                    WHERE hashes.hash IN ({hashes})
                    ORDER BY hashes.hash
                    '''.format(hashes=hquery,
                               meta_select=meta_select,
                               meta_joins=meta_joins),
                    params)

        return ResultBuilder(rows)

    def _make_condition(self, i, key, value):
        if isinstance(value, basestring):
            t = 'str'
            req = ('equal', value)
        elif isinstance(value, (int, long)):
            t = 'int'
            req = 'equal'
        elif isinstance(value, dict):
            req = dict(value)
            t = req.pop('type')
        else:
            raise TypeError(
                    "Query conditions should be dictionaries with the "
                    "format:\n"
                    "{'type': 'int/str/...', <condition>}")
        return ('i{i}.mvalue = :val{i}'.format(i=i),
                {'val%d' % i: value},
                t)


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
        def get_value(r):
            for t, n in MetadataStore._TYPES:
                v = r['mvalue_%s' % n]
                if v is not None:
                    return v
            else:
                raise Error("SQL query didn't return a value for "
                            "hash=%s, key=%s" % (r['hash'], r['mkey']))
        # We are outer joining, so a hash with no metadata will be returned as
        # a single row with mkey=NULL and everything but hash NULL
        if len(r) == 3 and r['mkey']:
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
