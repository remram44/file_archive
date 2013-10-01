import hashlib
import os
import shutil
import warnings

from .database import MetadataStore
from .errors import CreationError, InvalidStore, UsageWarning


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
        try:
            chunk = fileobj.read(CHUNKSIZE)
            while chunk:
                destobj.write(chunk)
                chunk = fileobj.read(CHUNKSIZE)
        except:
            os.remove(destination)
            raise


def hash_directory(path, visited=None):
    """Hashes a directory to a 40 hex character string.
    """
    h = hashlib.sha1()
    if visited is None:
        visited = set()
    if os.path.realpath(path) in visited:
        raise ValueError("Can't hash directory structure: loop detected at "
                         "%s" % path)
    visited.add(os.path.realpath(path))
    for f in os.listdir(path):
        pf = os.path.join(path, f)
        if os.path.isdir(pf):
            if os.path.islink(pf):
                warnings.warn("%s is a symbolic link, recursing on target "
                              "directory" % pf,
                              UsageWarning)
            h.update('dir %s %s\n' % (f, hash_directory(pf, visited)))
        else:
            if os.path.islink(pf):
                warnings.warn("%s is a symbolic link, using target file "
                              "instead" % pf,
                              UsageWarning)
            with open(pf, 'rb') as fd:
                h.update('file %s %s\n' % (f, hash_file(fd)))
    return h.hexdigest()


def copy_directory(sourcepath, destination):
    """Copies a directory recursively to a destination name.
    """
    # We don't display a warning for links, hash_directory() does that
    try:
        shutil.copytree(sourcepath, destination)
    except:
        shutil.rmtree(destination)
        raise


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
            exists = True
        else:
            exists = False
        try:
            if not exists:
                os.mkdir(path)
            os.mkdir(os.path.join(path, 'objects'))
        except OSError, e: # pragma: no cover
            raise CreationError("Could not create directories: %s: %s" % (
                    e.__class__.__name__, e.message))
        MetadataStore.create_db(os.path.join(path, 'database'))

    def close(self):
        self.metadata.close()
        self.metadata = None

    def open_file(self, filehash, binary=True):
        """Returns a file object for a given SHA1 hash.
        """
        try:
            return open(self.get_filename(filehash), 'rb' if binary else 'r')
        except IOError:
            raise KeyError("No file with hash %s" % filehash)

    def get_filename(self, filehash, make_dir=False):
        """Returns the file path for a given SHA1 hash.
        """
        if not isinstance(filehash, basestring):
            raise TypeError("hash should be a string, not %s" % type(filehash))
        dirname = os.path.join(self.store, filehash[:2])
        if not os.path.isdir(dirname):
            os.mkdir(dirname)
        return os.path.join(dirname, filehash[2:])

    def add_file(self, newfile, metadata):
        """Adds a file given a file object or path and dict of metadata.

        The file will be copied/written in the store, and an entry will be
        added to the database.

        Note that, if you pass a file object, it needs to support
        newfile.seek(0, os.SEEK_SET) as it will be read twice: once to compute
        its SHA1 hash, and a second time to write it to disk.
        """
        if isinstance(newfile, basestring):
            if os.path.islink(newfile):
                warnings.warn("%s is a symbolic link, using target file "
                              "instead" % newfile,
                              UsageWarning)
            newfile = open(newfile, 'rb')
        newfile.seek(0, os.SEEK_SET)
        filehash = hash_file(newfile)
        newfile.seek(0, os.SEEK_SET)
        storedfile = self.get_filename(filehash, make_dir=True)
        if os.path.exists(storedfile):
            raise KeyError("This file already exists in the store")
        copy_file(newfile, storedfile)
        try:
            self.metadata.add(filehash, metadata)
        except:
            os.remove(storedfile)
            raise
        return filehash

    def add_directory(self, newdir, metadata):
        """Adds a directory given a path and dict of metadata.

        The directory will be recursively copied to the store, and an entry
        will be added to the database.
        """
        if not isinstance(newdir, basestring):
            raise TypeError("newdir should be a string, not %s" % type(newdir))
        dirhash = hash_directory(newdir)
        storeddir = self.get_filename(dirhash, make_dir=True)
        if os.path.exists(storeddir):
            raise KeyError("This directory already exists in the store")
        copy_directory(newdir, storeddir)
        try:
            self.metadata.add(dirhash, metadata)
        except:
            shutil.rmtree(storeddir)
            raise
        return dirhash

    def remove(self, objecthash):
        """Removes a file or directory given its SHA1 hash.

        It is deleted from the store and removed from the database.
        """
        if isinstance(objecthash, Entry):
            objecthash = objecthash['hash']
        objectpath = self.get_filename(objecthash)
        if not os.path.exists(objectpath):
            raise KeyError("No object with hash %s" % objecthash)
        if os.path.isdir(objectpath):
            shutil.rmtree(objectpath)
        else:
            os.remove(objectpath)
        self.metadata.remove(objecthash)

    def get(self, objecthash):
        """Gets an Entry from a hash.
        """
        infos = self.metadata.get(objecthash) # Might raise KeyError
        return Entry(self, infos)

    def query_one(self, conditions):
        """Returns at most one Entry matching the conditions.

        Returns one of the Entry object matching the conditions or None.
        """
        infos = self.metadata.query_one(conditions)
        if infos is None:
            return None
        else:
            return Entry(self, infos)

    def query(self, conditions, limit=None):
        """Returns all the Entries matching the conditions.

        An EntryIterator is returned, with which you can access the different
        results.
        """
        infos = self.metadata.query_all(conditions, limit)
        return EntryIterator(self, infos)

    def verify(self):
        """Checks the integrity of the store.
        """
        # TODO : verify
