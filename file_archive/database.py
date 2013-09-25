import sqlite3

from .errors import InvalidStore


class MetadataStore(object):
    """The database holding metadata associated to SHA1 hashs.
    """
    def __init__(self, database):
        try:
            self.conn = sqlite3.connect(database)
            cur = self.conn.cursor()
            tables = cur.execute(
                u''' SELECT name FROM sqlite_master WHERE type = 'table' ''')
            if tables.fetchall() != [(u'metadata',)]:
                raise InvalidStore("Database doesn't have required structure")
        except sqlite3.Error, e:
            raise InvalidStore("Cannot access database: %s: %s" % (
                    e.__class__.__name__, e.message))

    def add(self, key, metadata):
        """Adds a hash and its metadata to the store.

        Raises KeyError if an entry already existed.
        """
        # TODO

    def remove(self, key):
        """Removes a hash and its metadata from the store.

        Raises KeyError if the entry didn't exist.
        """
        # TODO

    def query_one(self, conditions):
        """Returns at most one row matching the conditions, as a dict.

        The dict will have the 'hash' key plus all the stored metadata.
        """
        # TODO

    def query_all(self, conditions):
        """Returns an iterable of rows matching the conditions.

        Each row is a dict, with at least the 'hash' key.
        """
        # TODO
