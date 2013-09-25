import hashlib
import os

from .database import MetadataStore
from .errors import CreationError, InvalidStore


CHUNKSIZE = 4096


def hash_file(f):
    """Hashes a file to its 40 hex character SHA1.
    """
    h = hashlib.sha1()
    chunk = f.read(CHUNKSIZE)
    while chunk:
        h.update(chunk)
        chunk = f.read(CHUNKSIZE)
    return h.hexdigest()


def copy_file(fileobj, destination):
    """Copies a file object to a destination name.
    """
    with open(destination, 'wb') as destobj:
        chunk = fileobj.read(CHUNKSIZE)
        while chunk:
            destobj.write(chunk)
            chunk = fileobj.read(CHUNKSIZE)


class Entry(object):
    """Represents a file in the store, along with its metadata.

    Use open() to get a file object, or use entry['key'] to read metadata
    values (also available as the entry.metadata dict).
    """
    def __init__(self, store, infos):
        self.filename = store.get_filename(infos['hash'])
        self.metadata = infos

    def __getitem__(self, key):
        return self.metadata[key]

    def open(self, binary=True):
        return open(self.filename, 'rb' if binary else 'r')


class EntryIterator(object):
    """Iterator returned by query().

    You can iterate on this to read all matching entries.
    """
    def __init__(self, store, infos):
        self.store = store
        self.infos = infos

    def __iter__(self):
        return self

    def next(self):
        return Entry(self.store, self.infos.next())


# TODO : handle directories

class FileStore(object):
    """Represents a file store.
    """
    def __init__(self, path):
        self.store = os.path.join(path, 'objects')
        if not os.path.isdir(self.store):
            raise InvalidStore("objects is not a directory")
        db = os.path.join(path, 'database')
        if not os.path.isfile(db):
            raise InvalidStore("database is not a file")
        self.metadata = MetadataStore(db)

    @staticmethod
    def create_store(path):
        if os.path.exists(path):
            if not os.path.isdir(path) or os.listdir(path):
                raise CreationError("Path is not a directory or is not empty")
        try:
            os.mkdir(path)
            os.mkdir(os.path.join(path, 'objects'))
        except OSError, e:
            raise CreationError("Could not create directories: %s: %s" % (
                    e.__class__.__name__))
        MetadataStore.create_db(os.path.join(path, 'database'))

    def open_file(self, filehash):
        """Returns a file object for a given SHA1 hash.
        """
        try:
            open(self.get_filename(filehash), 'rb')
        except IOError:
            raise KeyError("No file with hash %s" % filehash)

    def get_filename(self, filehash):
        """Returns the file path for a given SHA1 hash.
        """
        if not isinstance(hash, basestring):
            raise TypeError("hash should be a string, not %s" % type(filehash))
        return os.path.join(self.store, filehash[:2], filehash[2:])

    def add_file(self, newfile, metadata):
        """Adds a file given a file object or path and dict of metadata.

        The file will be copied/written in the store, and an entry will be
        added to the database.
        """
        if isinstance(newfile, basestring):
            newfile = open(newfile, 'rb')
        newfile.seek(0, os.SEEK_SET)
        filehash = hash_file(newfile)
        copy_file(newfile, self.get_filename(filehash))
        self.metadata.add(filehash, metadata)

    def remove_file(self, filehash):
        """Removes a file given its SHA1 hash.

        It is deleted from the store and removed from the database.
        """
        if isinstance(filehash, Entry):
            filehash = filehash['hash']
        os.remove(self.get_filename(filehash))
        self.metadata.remove(filehash)

    def query_one(self, conditions):
        """Returns at most one Entry matching the conditions.

        Returns one of the Entry object matching the conditions or None.
        """
        infos = self.metadata.query_one(conditions)
        if infos is None:
            return None
        else:
            return Entry(self, infos)

    def query(self, conditions):
        """Returns all the Entries matching the conditions.

        An EntryIterator is returned, with which you can access the different
        results.
        """
        infos = self.metadata.query_all(conditions)
        return EntryIterator(self, infos)
