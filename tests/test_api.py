import contextlib
import os
import shutil
import tempfile

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from file_archive import FileStore
from file_archive.errors import CreationError


@contextlib.contextmanager
def temp_dir(make=True):
    path = tempfile.mkdtemp(prefix='test_file_archive_')
    try:
        if make:
            yield path
        else:
            yield path + 'internal'
    finally:
        shutil.rmtree(path)


class TestCreate(unittest.TestCase):
    """Tests the creation of a new file store on disk.
    """
    def test_create(self):
        with temp_dir(False) as d:
            FileStore.create_store(d)
            self.assertTrue(os.path.isdir(d))
            self.assertTrue(os.path.isfile(os.path.join(d, 'database')))
        with temp_dir(True) as d:
            FileStore.create_store(d)
            self.assertTrue(os.path.isfile(os.path.join(d, 'database')))

    def test_create_nonempty(self):
        with temp_dir() as d:
            with open(os.path.join(d, 'somefile'), 'wb') as fp:
                fp.write("I'm not empty\n")
            with self.assertRaises(CreationError):
                FileStore.create_store(d)
        with temp_dir() as d:
            FileStore.create_store(d)
            with self.assertRaises(CreationError):
                FileStore.create_store(d)
