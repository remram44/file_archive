import itertools
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
            if set(tables.fetchall()) != set[(u'metadata',), (u'hashes',)]:
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
                        hash VARCHAR(40),
                        creation_time DATETIME)
                    ''')
            conn.execute(u'''
                    CREATE TABLE metadata(
                        hash VARCHAR(40),
                        key VARCHAR(255),
                        value VARCHAR(255))
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
                    INSERT INTO hash(hash, creation_time)
                    VALUES(:hash, datetime())
                    ''',
                    {'hash': key})
            cur.executemany(u'''
                    INSERT INTO metadata(hash, key, value)
                    VALUES(:hash, :key, :value)
                    ''',
                    itertools.chain((('hash', key),), metadata.iteritems()))
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
        # TODO

    def query_all(self, conditions):
        """Returns an iterable of rows matching the conditions.

        Each row is a dict, with at least the 'hash' key.
        """
        # TODO
