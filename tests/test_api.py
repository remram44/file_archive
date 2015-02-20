from __future__ import division, unicode_literals

import os
import platform
import shutil
import tempfile
import warnings

try:
    import unittest2 as unittest
except ImportError:
    import unittest

import file_archive
from file_archive.compat import StringIO

from .common import temp_dir, temp_warning_filter


requires_symlink = unittest.skipIf(platform.system() == 'Windows',
                                   "Symlinks unavailable")


class TestInternals(unittest.TestCase):
    """Tests internal functions.
    """
    def test_buffered_reader(self):
        def chunks(s):
            return list(file_archive.BufferedReader(StringIO(s)))

        old_chunk_size = file_archive.CHUNKSIZE
        file_archive.CHUNKSIZE = 4
        try:
            self.assertEqual(chunks(''), [])
            self.assertEqual(chunks('a'), ['a'])
            self.assertEqual(chunks('abcd'), ['abcd'])
            self.assertEqual(chunks('abcde'), ['abcd', 'e'])
            self.assertEqual(chunks('abcdefghijkl'), ['abcd', 'efgh', 'ijkl'])
            self.assertEqual(chunks('abcdefghij'), ['abcd', 'efgh', 'ij'])
        finally:
            file_archive.CHUNKSIZE = old_chunk_size

    @requires_symlink
    def test_relativize_link(self):
        with temp_dir() as t:
            relativize_link = file_archive.relativize_link
            join = os.path.join

            d = join(t, 'inner')
            os.mkdir(d)
            i = join(d, 'dirI')
            os.mkdir(i)
            j = join(d, 'dirJ')
            os.mkdir(j)
            os.symlink(join(d, 'file'), join(i, 'link1'))
            os.symlink('../file', join(i, 'link1r'))
            os.symlink(join(j, 'file'), join(i, 'link2'))
            os.symlink('../dirJ/file', join(i, 'link2r'))
            os.symlink(join(j, 'file'), join(d, 'link3'))
            os.symlink('dirJ/file', join(d, 'link3r'))
            os.symlink(join(t, 'file'), join(i, 'link4'))
            os.symlink('../../file', join(i, 'link4r'))
            os.symlink(join(t, 'file'), join(d, 'link5'))
            os.symlink('../file', join(d, 'link5r'))

            self.assertEqual(relativize_link(join(i, 'link1'), d),
                             '../file')
            self.assertEqual(relativize_link(join(i, 'link2'), d),
                             '../dirJ/file')
            self.assertEqual(relativize_link(join(d, 'link3'), d),
                             'dirJ/file')
            self.assertEqual(relativize_link(join(i, 'link4'), d),
                             None)
            self.assertEqual(relativize_link(join(d, 'link5'), d),
                             None)


class TestCreate(unittest.TestCase):
    """Tests the creation of a new file store on disk.
    """
    def test_create(self):
        with temp_dir(False) as d:
            file_archive.FileStore.create_store(d)
            self.assertTrue(os.path.isdir(d))
            self.assertTrue(os.path.isfile(os.path.join(d, 'database')))
        with temp_dir(True) as d:
            file_archive.FileStore.create_store(d)
            self.assertTrue(os.path.isfile(os.path.join(d, 'database')))

    def test_create_nonempty(self):
        with temp_dir() as d:
            with open(os.path.join(d, 'somefile'), 'wb') as fp:
                fp.write(b"I'm not empty\n")
            with self.assertRaises(file_archive.CreationError):
                file_archive.FileStore.create_store(d)
        with temp_dir() as d:
            file_archive.FileStore.create_store(d)
            with self.assertRaises(file_archive.CreationError):
                file_archive.FileStore.create_store(d)


class TestOpen(unittest.TestCase):
    def test_open_invalid(self):
        with temp_dir() as d:
            with self.assertRaises(file_archive.InvalidStore):
                file_archive.FileStore(d)
        with temp_dir() as d:
            os.mkdir(os.path.join(d, 'objects'))
            with self.assertRaises(file_archive.InvalidStore):
                file_archive.FileStore(d)
        with temp_dir() as d:
            with open(os.path.join(d, 'database'), 'wb'):
                pass
            with self.assertRaises(file_archive.InvalidStore):
                file_archive.FileStore(d)


class TestStore(unittest.TestCase):
    """Tests opening the store and using it.
    """
    def setUp(self):
        self.path = tempfile.mkdtemp(prefix='test_file_archive_')
        file_archive.FileStore.create_store(self.path)
        self.store = file_archive.FileStore(self.path)
        testfiles = os.path.join(os.path.dirname(__file__), 'testfiles')
        self.t = lambda f: os.path.join(testfiles, f)

    def tearDown(self):
        self.store.close()
        self.store = None
        shutil.rmtree(self.path)

    def test_req_empty(self):
        self.assertEqual(list(self.store.query({})), [])

    def test_putfile(self):
        entry1 = self.store.add_file(self.t('file1.bin'), {'a': 'b'})
        h1 = 'fce92fa2647153f7d696a3c1884d732290273102'
        self.assertEqual(entry1['hash'], h1)
        self.assertTrue(os.path.isfile(os.path.join(
                self.path,
                'objects',
                'fc',
                'e92fa2647153f7d696a3c1884d732290273102')))
        self.assertEqual(
                self.store.get(h1).metadata,
                {'hash': h1, 'a': 'b'})

    def test_put_file_twice(self):
        self.assertIsNotNone(self.store.add_file(self.t('file1.bin'), {}))
        with self.assertRaises(KeyError):
            self.store.add_file(self.t('file1.bin'), {})

    def test_put_dir_twice(self):
        self.assertIsNotNone(self.store.add_directory(self.t('dir3'), {'a': 'b'}))
        with self.assertRaises(KeyError):
            self.store.add_directory(self.t('dir3'), {})

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
                 ('file5.bin', {'e': 'aa', 'f': 41}),
            ]

        h = []
        meta = {}
        for f, m in files:
            if f == 'file1.bin':
                r = self.store.add_file(self.t(f), m)
            elif f == 'file2.bin':
                with open(self.t(f), 'rb') as fp:
                    r = self.store.add_file(fp, m)
            elif f == 'dir3':
                r = self.store.add(self.t(f), m)
            elif f == 'dir4':
                r = self.store.add_directory(self.t(f), m)
            else:
                r = self.store.add(self.t(f), m)
            h.append(r['hash'])
            meta[r['hash']] = r.metadata

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

    def test_invalid_add(self):
        with self.assertRaises(ValueError):
            self.store.add(self.t('file1.bin'), {'k': {'whatsthis': 'value'}})
        with self.assertRaises(ValueError):
            self.store.add(self.t('dir3'), {'k': {'whatsthis': 'value'}})
        self.assertEqual(list(self.store.query({})), [])

    def test_badpath(self):
        with self.assertRaises(TypeError):
            self.store.add_directory(2, {})
        with self.assertRaises(TypeError):
            self.store.add(2, {})
        self.assertEqual(list(self.store.query({})), [])

    def test_wrongpath(self):
        with self.assertRaises(ValueError):
            self.store.add_directory('/this/path/doesnt/exist', {})

    def test_open(self):
        e = self.store.add_file(self.t('file1.bin'), {'findme': 'here'})
        h = e['hash']
        entry = self.store.query_one({'findme': 'here'})
        self.assertEqual(entry.metadata, {'hash': h, 'findme': 'here'})
        self.assertEqual(
                os.path.realpath(entry.filename),
                os.path.realpath(os.path.join(
                        self.path,
                        'objects',
                        h[:2], h[2:])))
        c = (b'this is some\n'
             b'random content\n'
             b'note LF line endings\n')
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

    @requires_symlink
    def test_internal_symlink(self):
        with temp_dir() as d:
            shutil.copyfile(self.t('file1.bin'), os.path.join(d, 'file'))
            os.mkdir(os.path.join(d, 'dir'))
            os.symlink(os.path.join(d, 'file'), os.path.join(d, 'dir', 'link'))
            entry = self.store.add_directory(d, {})
            path = entry.filename
            c = (b'this is some\n'
                 b'random content\n'
                 b'note LF line endings\n')
            with open(os.path.join(path, 'file'), 'rb') as fp:
                self.assertEqual(fp.read(), c)
            with open(os.path.join(path, 'dir', 'link'), 'rb') as fp:
                self.assertEqual(fp.read(), c)
            self.assertTrue(os.path.islink(os.path.join(path, 'dir', 'link')))
            self.assertEqual(os.readlink(os.path.join(path, 'dir', 'link')),
                             '../file')

    @requires_symlink
    def test_external_symlink(self):
        def test_warning(warns):
            self.assertEqual(len(warns), 1)
            self.assertIs(type(warns[0].message), file_archive.UsageWarning)
            self.assertTrue(warns[0].message.args[0].endswith(
                    "is a symbolic link, using target file instead"))
        with temp_dir() as d:
            os.symlink(self.t('file1.bin'), os.path.join(d, 'link'))
            with warnings.catch_warnings(record=True) as warns:
                self.store.add(d, {})
            test_warning(warns)
            with warnings.catch_warnings(record=True) as warns:
                self.store.add_file(os.path.join(d, 'link'), {})
            test_warning(warns)

    @requires_symlink
    def test_symlink_recursive(self):
        with temp_dir() as d:
            shutil.copyfile(self.t('file1.bin'), os.path.join(d, 'file'))
            os.symlink(d, os.path.join(d, 'link'))
            with temp_warning_filter():
                warnings.filterwarnings(
                        'ignore',
                        '.*is a symbolic link, recursing on target directory$',
                        file_archive.UsageWarning)
                with self.assertRaises(ValueError):
                    self.store.add_directory(d, {'some': 'data'})
