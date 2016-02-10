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
from file_archive.compat import BytesIO

from tests.common import temp_dir, temp_warning_filter


requires_symlink = unittest.skipIf(platform.system() == 'Windows',
                                   "Symlinks unavailable")


class TestInternals(unittest.TestCase):
    """Tests internal functions.
    """
    def test_buffered_reader(self):
        def chunks(s):
            return list(file_archive.BufferedReader(BytesIO(s)))

        old_chunk_size = file_archive.CHUNKSIZE
        file_archive.CHUNKSIZE = 4
        try:
            self.assertEqual(chunks(b''), [])
            self.assertEqual(chunks(b'a'), [b'a'])
            self.assertEqual(chunks(b'abcd'), [b'abcd'])
            self.assertEqual(chunks(b'abcde'), [b'abcd', b'e'])
            self.assertEqual(chunks(b'abcdefghijkl'),
                             [b'abcd', b'efgh', b'ijkl'])
            self.assertEqual(chunks(b'abcdefghij'), [b'abcd', b'efgh', b'ij'])
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
        testfiles = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'testfiles')
        self.t = lambda f: os.path.join(testfiles, f)

    def tearDown(self):
        self.store.close()
        self.store = None
        shutil.rmtree(self.path)

    def test_req_empty(self):
        self.assertEqual(list(self.store.query({})), [])

    def test_putfile(self):
        with self.assertRaises(ValueError):
            self.store.add_file(
                self.t('file1.bin'),
                {'a': {'type': 'str', 'value': 'b', 'other': 'dont'}})
        with self.assertRaises(TypeError):
            self.store.add_file(self.t('file1.bin'), {'a': object()})

        entry1 = self.store.add_file(self.t('file1.bin'),
                                     {'a': {'type': 'str', 'value': 'b'}})
        h1 = 'fce92fa2647153f7d696a3c1884d732290273102'
        o1 = '8ce67dc4c67401ff8122ecebc98ecee506211f88'
        self.assertEqual(entry1['hash'], h1)
        self.assertTrue(os.path.isfile(os.path.join(
            self.path,
            'objects',
            'fc',
            'e92fa2647153f7d696a3c1884d732290273102')))
        self.assertEqual(
            self.store.get(o1).metadata,
            {'hash': h1, 'a': 'b'})

    def test_put_file_twice(self):
        self.assertIsNotNone(self.store.add_file(self.t('file1.bin'), {}))
        self.assertIsNotNone(self.store.add_file(self.t('file1.bin'), {}))
        self.assertIsNotNone(self.store.add_file(self.t('file1.bin'),
                                                 {'k': 'v'}))

        self.assertEqual(os.listdir(os.path.join(self.path, 'objects')),
                         ['fc'])
        self.assertEqual(os.listdir(os.path.join(self.path, 'objects', 'fc')),
                         ['e92fa2647153f7d696a3c1884d732290273102'])

    def test_put_dir_twice(self):
        self.assertIsNotNone(self.store.add_directory(self.t('dir3'),
                                                      {'a': 'b'}))
        self.assertIsNotNone(self.store.add_directory(self.t('dir3'), {}))
        self.assertIsNotNone(self.store.add_directory(self.t('dir3'), {}))

        self.assertEqual(os.listdir(os.path.join(self.path, 'objects')),
                         ['ed'])
        self.assertEqual(os.listdir(os.path.join(self.path, 'objects', 'ed')),
                         ['1e24cdb080c9b870598572ee645fb358f8d7dc'])

    def test_reqs(self):
        def assert_one(cond, expected):
            entry = self.store.query_one(cond)
            if entry is None:
                self.assertIsNone(expected)
            else:
                self.assertEqual(entry.objectid, expected)
                self.assertEqual(entry.metadata, meta[expected])

        def assert_many(cond, expected):
            entries = self.store.query(cond)
            objectids = set(entry.objectid for entry in entries)
            self.assertEqual(objectids, set(expected))
            for entry in entries:
                self.assertEqual(entry.metadata, meta[entry.objectid])

        files = [
            ('file1.bin', '6de19c2c8a867f2d9a2f663e036a6a70be8da205',
             {}),
            ('file2.bin', '30df4f59cb6403af6b153306edd7f0d2d48afbb2',
             {'a': 'aa', 'c': 12, 'd': 'common'}),
            ('dir3', 'be511e1f41f5342a01bbc25bf3e5efeaf4b4502f',
             {'a': 'bb', 'c': 41}),
            ('dir4', 'ba1f71ab8c587ce78f0209c11e1ab742ba16b7ef',
             {'c': '12', 'd': 'common'}),
            ('file5.bin', '9b54725b357d9c7dd58ca83708ca4e73c7e44fd3',
             {'e': 'aa', 'f': 41}),
        ]

        ids = []
        meta = {}
        for f, objectid, m in files:
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
            ids.append(r.objectid)
            self.assertEqual(objectid, r.objectid)
            meta[r.objectid] = r.metadata

        assert_one({'c': 41}, ids[2])
        assert_many({'c': 41}, [ids[2]])
        assert_many({'c': '41'}, [])
        assert_one({'c': '41'}, None)
        assert_many({}, ids)
        assert_many({'c': '12'}, [ids[3]])
        assert_many({'d': 'common'}, [ids[1], ids[3]])
        assert_many({'a': 'aa', 'c': 12}, [ids[1]])
        assert_many({'a': 'bb', 'c': 12}, [])
        assert_many({'a': 'aa', 'c': 5}, [])

        assert_many({'c': {'type': 'int', 'gt': 5, 'lt': 15}}, [ids[1]])
        assert_many({'c': {'type': 'int', 'gt': 5}}, [ids[1], ids[2]])

        with self.assertRaises(TypeError):
            self.store.query({'c': {'whatsthis': 'value'}})
        with self.assertRaises(ValueError):
            self.store.query({'c': {'type': 'int', 'whatsthis': 'value'}})

        assert_many({'a': {'type': 'str'}}, [ids[1], ids[2]])
        assert_one({'f': {'type': 'int'}}, ids[4])

        self.store.remove(ids[1])
        assert_many({'a': 'aa'}, [])
        assert_many({'d': 'common'}, [ids[3]])
        self.store.remove(ids[3])
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
        oid = e.objectid
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
        fp = self.store.open_file(oid)
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
            self.store.remove(oid)
        with self.assertRaises(KeyError):
            self.store.get(oid)

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
