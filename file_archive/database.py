from __future__ import division, unicode_literals

import sqlite3

from file_archive.compat import PY3, string_types, int_types
from file_archive.errors import Error, CreationError, InvalidStore


__all__ = ['MetadataStore']


if not PY3:
    class Row(sqlite3.Row):
        """Version of sqlite3.Row that doesn't choke on unicode column names.
        """
        def __getitem__(self, idx):  # pragma: no cover
            if isinstance(idx, unicode):
                idx = idx.encode('ascii')
            return sqlite3.Row.__getitem__(self, idx)
else:
    Row = sqlite3.Row


def normalize_metadata(metadata):
    result = {}
    for mkey, mvalue in metadata.items():
        if isinstance(mvalue, string_types):
            t = 'str'
        elif isinstance(mvalue, int_types):
            t = 'int'
        elif isinstance(mvalue, dict):
            r = dict(mvalue)
            try:
                t = r.pop('type')
                mvalue = r.pop('value')
                if r:
                    raise KeyError
            except KeyError:
                raise ValueError("Metadata values should be "
                                 "dictionaries with the format:\n"
                                 "{'type': 'int/str/...', "
                                 "'value': <value>}")
        else:
            raise TypeError(
                    "Metadata values should be int, string, or dictionaries "
                    "with the format:\n"
                    "{'type': 'int/str/...', 'value': <value>}")
        if isinstance(mvalue, bytes):
            mvalue = mvalue.decode('ascii')
        result[mkey] = {'type': t, 'value': mvalue}
    return result


class MetadataStore(object):
    """The database holding metadata associated to SHA1 hashs.
    """
    _TYPES = [('TEXT', 'str'), ('INTEGER', 'int')]

    def __init__(self, database):
        try:
            self.conn = sqlite3.connect(database)
            self.conn.row_factory = Row
            cur = self.conn.cursor()
            tables = cur.execute('''
                    SELECT name FROM sqlite_master WHERE type = 'table'
                    ''')
            tables = set(r['name'] for r in tables.fetchall())
            if tables != set(['metadata']):
                raise InvalidStore("Database doesn't have required structure")
        except sqlite3.Error as e:
            raise InvalidStore("Cannot access database: %s: %s" % (
                    e.__class__.__name__, e.message))

    @staticmethod
    def create_db(database):
        try:
            conn = sqlite3.connect(database)
            query = '''
                    CREATE TABLE metadata(
                        objectid VARCHAR(40) NOT NULL,
                        mkey VARCHAR(255) NULL
                    '''
            indexes = [
                    'CREATE INDEX id_idx ON metadata(objectid)',
                    'CREATE INDEX mkey_idx ON metadata(mkey)']

            for datatype, name in MetadataStore._TYPES:
                query += '''
                        , mvalue_{name} {type} NULL
                        '''.format(name=name, type=datatype)
                indexes.append('''
                        CREATE INDEX mvalue_{name} ON metadata(mvalue_{name})
                        '''.format(name=name))
            query += ')'

            cur = conn.cursor()
            cur.execute(query)
            for idx_query in indexes:
                cur.execute(idx_query)

            conn.commit()
            conn.close()
        except sqlite3.Error as e:  # pragma: no cover
            raise CreationError("Could not create database: %s: %s" % (
                    e.__class__.__name__, e.message))

    def close(self):
        self.conn.commit()
        self.conn.close()

    def add(self, objectid, metadata):
        """Adds an object to the store.

        Returns True if it wasn't already stored.
        """
        assert 'hash' in metadata
        metadata = normalize_metadata(metadata)
        cur = self.conn.cursor()
        try:
            cur.execute(
                    '''
                    SELECT objectid FROM metadata
                    WHERE objectid = :objectid
                    LIMIT 1
                    ''',
                    {'objectid': objectid})
            if cur.fetchone() is not None:
                return False
            for mkey, mvalue in metadata.items():
                t = mvalue['type']
                v = mvalue['value']
                cur.execute(
                        '''
                        INSERT INTO metadata(objectid, mkey, mvalue_{name})
                        VALUES(:objectid, :key, :value)
                        '''.format(name=t),
                        {'objectid': objectid, 'key': mkey, 'value': v})
            self.conn.commit()
            return True
        except:
            self.conn.rollback()
            raise

    def remove(self, objectid):
        """Removes an object from the store.

        Raises KeyError if the entry didn't exist.
        """
        cur = self.conn.cursor()
        try:
            cur.execute(
                    '''
                    DELETE FROM metadata WHERE objectid = :objectid
                    ''',
                    {'objectid': objectid})
            if not cur.rowcount:
                raise KeyError(objectid)
            self.conn.commit()
        except:
            self.conn.rollback()
            raise

    def get(self, objectid):
        """Gets an entry from its objectid, as a dict.
        """
        cur = self.conn.cursor()
        rows = cur.execute(
                '''
                SELECT * FROM metadata
                WHERE objectid = :objectid
                ''',
                {'objectid': objectid})
        result = ResultBuilder(rows)
        try:
            objectid_, metadata = next(result)
            return metadata
        except StopIteration:
            raise KeyError("No entry with this objectid")

    def has_filehash(self, filehash):
        """Checks for at least one entry with the given file hash.

        File should be garbage-collected if no entry refers to it.
        """
        cur = self.conn.cursor()
        rows = cur.execute(
                '''
                SELECT * FROM metadata
                WHERE mkey = 'hash' AND mvalue_str = :filehash
                ''',
                {'filehash': filehash})
        try:
            next(rows)
            return True
        except StopIteration:
            return False

    def query_one(self, conditions):
        """Returns at most one entry matching the conditions, as a dict.

        Returns objectid, metadata:dict

        The metadata dict will have the 'hash' key plus all the stored
        metadata.

        `conditions` is a dictionary of metadata that need to be included in
        the actual dict of each entry.
        """
        rows = self.query_all(conditions, limit=1)
        try:
            return next(rows)
        except StopIteration:
            return None, None

    def query_all(self, conditions, limit=None):
        """Returns an iterable of rows matching the conditions.

        Each row is a pair (objectid, metadata), where metadata will have the
        'hash' key plus all the stored metadata.

        `conditions` is a dictionary of metadata that need to be included in
        the actual dict of each entry.
        """
        # Build the LIMIT part from the limit arg (number or None)
        if limit is not None:
            limit = 'LIMIT %d' % limit
        else:
            limit = ''

        cur = self.conn.cursor()
        if not conditions:
            hquery = '''
                    SELECT DISTINCT objectid
                    FROM metadata
                    {limit}
                    '''.format(limit=limit)
            params = {}
        else:
            conditems = self._make_conditions(conditions)
            i, key, cond0, params = next(conditems)
            hquery = '''
                    SELECT i0.objectid
                    FROM metadata i0
                    '''
            params['key0'] = key
            for i, key, cond, prms in conditems:
                hquery += '''
                        INNER JOIN metadata i{i} ON i0.objectid = i{i}.objectid
                            AND i{i}.mkey = :key{i} {cond}
                        '''.format(i=i, cond='AND ' + cond if cond else '')
                params['key%d' % i] = key
                params.update(prms)
            hquery += '''
                    WHERE i0.mkey = :key0 {cond}
                    {limit}
                    '''.format(cond='AND ' + cond0 if cond0 else '',
                               limit=limit)

        # And we put that in the query
        rows = cur.execute(
                '''
                SELECT *
                FROM metadata
                WHERE objectid IN ({ids})
                ORDER BY objectid
                '''.format(ids=hquery),
                params)

        return ResultBuilder(rows)

    def _make_conditions(self, conditions):
        for i, (key, value) in enumerate(conditions.items()):
            t = None
            if isinstance(value, string_types):
                t = 'str'
                req = [('equal', value)]
            elif isinstance(value, int_types):
                t = 'int'
                req = [('equal', value)]
            elif isinstance(value, dict) and not value:
                # Empty dict: key exist with any type or value
                req = value
            elif isinstance(value, dict):
                req = dict(value)
                try:
                    t = req.pop('type')
                except KeyError:
                    raise TypeError("Query conditions should include key "
                                    "'type'")
                req = iter(req.items())
                if t not in ('str', 'int'):
                    raise TypeError("Unknown data type %r" % t)
            else:
                raise TypeError(
                        "Query conditions should be dictionaries with the "
                        "format:\n"
                        "{'type': 'int/str/...', <condition>}")

            conds = []
            params = {}
            if req:
                var = 'i{i}.mvalue_{t}'.format(i=i, t=t)
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
            elif t is not None:
                # Just check type
                conds = ['{var} IS NOT NULL'.format(
                         var='i{i}.mvalue_{t}'.format(i=i, t=t))]
            yield (i,
                   key,
                   ' AND '.join(conds),
                   params)


class ResultBuilder(object):
    """This regroups rows for key-values of a single entry into one dict.

    Example:
    +--------+----+------+
    |objectid|mkey|mvalue|    [
    +--------+----+------+     'aaaa', {'hash': 'xxxx', 'one': 11, 'two': 12},
    |  aaaa  |one |  11  | =>  'bbbb', {'hash': 'yyyy', 'one': 21, 'six': 26},
    |  aaaa  |two |  12  |    ]
    |  bbbb  |one |  21  |
    |  bbbb  |six |  26  |
    +--------+----+------+
    """
    def __init__(self, rows):
        self.rows = iter(rows)
        self.record = None

    def __iter__(self):  # pragma: no cover
        return self

    def next(self):
        if self.rows is None:
            raise StopIteration
        if self.record is None:
            r = next(self.rows)  # Might raise StopIteration
        else:
            r = self.record
        objectid = r['objectid']

        def get_value(r):
            for datatype, name in MetadataStore._TYPES:
                v = r['mvalue_%s' % name]
                if v is not None:
                    return v
            else:  # pragma: no cover
                raise Error("SQL query didn't return a value for "
                            "objectid=%s, key=%s" % (r['objectid'], r['mkey']))

        # We are outer joining, so an objectid with no metadata will be
        # returned as a single row with mkey and everything but objectid NULL
        if len(r) > 1 and r['mkey']:
            dct = {r['mkey']: get_value(r)}
        else:
            dct = {}

        for r in self.rows:
            if r['objectid'] != objectid:
                self.record = r
                assert 'hash' in dct
                return objectid, dct
            dct[r['mkey']] = get_value(r)
        else:
            self.rows = None
        assert 'hash' in dct
        return objectid, dct
    __next__ = next
