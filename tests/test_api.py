import contextlib
import os
import shutil
import tempfile

try:
    import unittest2 as unittest
except ImportError:
    import unittest

from file_archive import FileStore
from file_archive.errors import CreationError, InvalidStore


@contextlib.contextmanager
def temp_dir(make=True):
    path = tempfile.mkdtemp(prefix='test_file_archive_')
    try:
        if make:
            yield path
        else:
            yield os.path.join(path, 'internal')
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


class TestOpen(unittest.TestCase):
    def test_open_invalid(self):
        with temp_dir() as d:
            with self.assertRaises(InvalidStore):
                FileStore(d)
        with temp_dir() as d:
            os.mkdir(os.path.join(d, 'objects'))
            with self.assertRaises(InvalidStore):
                FileStore(d)
        with temp_dir() as d:
            with open(os.path.join(d, 'database'), 'wb'):
                pass
            with self.assertRaises(InvalidStore):
                FileStore(d)


class TestStore(unittest.TestCase):
    """Tests opening the store and using it.
    """
    def setUp(self):
        self.path = tempfile.mkdtemp(prefix='test_file_archive_')
        FileStore.create_store(self.path)
        self.store = FileStore(self.path)
        testfiles = os.path.join(os.path.dirname(__file__), 'testfiles')
        self.t = lambda f: os.path.join(testfiles, f)

    def tearDown(self):
        self.store.close()
        self.store = None
        shutil.rmtree(self.path)

    def test_req_empty(self):
        self.assertEqual(list(self.store.query({})), [])

    def test_putfile(self):
        h1 = self.store.add_file(self.t('file1.bin'), {'a': 'b'})
        self.assertEqual(h1, '6edc650f52e26ce867b3765e0563dc3e445cdaa9')
        self.assertTrue(os.path.isfile(os.path.join(
                self.path,
                'objects',
                '6e',
                'dc650f52e26ce867b3765e0563dc3e445cdaa9')))
        self.assertEqual(
                self.store.get(h1).metadata,
                {'hash': h1, 'a': 'b'})

    def test_put_twice(self):
        self.assertIsNotNone(self.store.add_file(self.t('file1.bin'), {}))
        with self.assertRaises(KeyError):
            self.store.add_file(self.t('file1.bin'), {})

    def test_reqs(self):
        def assert_one(cond, expected):
            entry = self.store.query_one(cond)
            if entry is None:
                self.assertIsNone(expected)
            else:
                self.assertEqual(entry['hash'], expected)
                self.assertEqual(entry.metadata, meta[expected])
        def assert_many(cond, expected):
            entries = self.store.query(cond)
            hashes = set(entry['hash'] for entry in entries)
            self.assertEqual(hashes, set(expected))
            for entry in entries:
                self.assertEqual(entry.metadata, meta[entry['hash']])

        files = [
                ('file1.bin', {}),
                ('file2.bin', {'a': 'aa', 'c': 12, 'd': 'common'}),
                 ('dir3', {'a': 'bb', 'c': 41}),
                 ('dir4', {'c': '12', 'd': 'common'}),
            ]

        h = []
        meta = {}
        for f, m in files:
            if f.startswith('dir'):
                r = self.store.add_directory(self.t(f), m)
            elif f != 'file2.bin':
                r = self.store.add_file(self.t(f), m)
            else:
                with open(self.t(f), 'rb') as fp:
                    r = self.store.add_file(fp, m)
            h.append(r)
            m['hash'] = r
            meta[r] = m

        assert_one({'c': 41}, h[2])
        assert_many({'c': 41}, [h[2]])
        assert_many({'c': '41'}, [])
        assert_one({'c': '41'}, None)
        assert_many({}, h)
        assert_many({'c': '12'}, [h[3]])
        assert_many({'d': 'common'}, [h[1], h[3]])
        assert_many({'a': 'aa', 'c': 12}, [h[1]])
        assert_many({'a': 'bb', 'c': 12}, [])
        assert_many({'a': 'aa', 'c': 5}, [])

        assert_many({'c': {'type': 'int', 'gt': 5, 'lt': 15}}, [h[1]])
        assert_many({'c': {'type': 'int', 'gt': 5}}, [h[1], h[2]])

        with self.assertRaises(TypeError):
            self.store.query({'c': {'whatsthis': 'value'}})
        with self.assertRaises(ValueError):
            self.store.query({'c': {'type': 'int', 'whatsthis': 'value'}})

        self.store.remove(h[1])
        assert_many({'a': 'aa'}, [])
        assert_many({'d': 'common'}, [h[3]])
        self.store.remove(h[3])
        assert_many({'d': 'common'}, [])

    def test_open(self):
        h = self.store.add_file(self.t('file1.bin'), {'findme': 'here'})
        entry = self.store.query_one({'findme': 'here'})
        self.assertEqual(entry.metadata, {'hash': h, 'findme': 'here'})
        self.assertEqual(
                os.path.realpath(entry.filename),
                os.path.realpath(os.path.join(
                        self.path,
                        'objects',
                        h[:2], h[2:])))
        c = ('this is some\n'
             'random content\n'
             'note LF line endings\n')
        fp = entry.open()
        try:
            self.assertEqual(fp.read(), c)
        finally:
            fp.close()
        fp = self.store.open_file(h)
        try:
            self.assertEqual(fp.read(), c)
        finally:
            fp.close()
        with self.assertRaises(KeyError):
            self.store.open_file('notahash')
        with self.assertRaises(TypeError):
            self.store.open_file(42)
        self.store.remove(entry)
        self.assertIsNone(self.store.query_one({'findme': 'here'}))
        with self.assertRaises(KeyError):
            self.store.remove(h)
        with self.assertRaises(KeyError):
            self.store.get(h)
