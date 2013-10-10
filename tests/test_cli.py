import os
import sys
import tempfile
from file_archive import FileStore
import shutil
try:
    import unittest2 as unittest
except ImportError:
    import unittest

from file_archive.compat import StringIO
import file_archive.main

from .common import temp_dir


def run_program(*args, **kwargs):
    out, err = StringIO(), StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    try:
        file_archive.main.main(list(args))
        raise Exception("Program didn't exit")
    except SystemExit as e:
        return e.code
    # We might get another exception here, which will be reported as error by
    # unittest
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        def read(f):
            f.seek(0, os.SEEK_SET)
            return (l.rstrip('\r\n') for l in f)
        if 'out' in kwargs:
            kwargs['out'].extend(read(out))
        if 'err' in kwargs:
            kwargs['err'].extend(read(err))


class TestUsage(unittest.TestCase):
    def test_noargs(self):
        self.assertEqual(run_program(), 1)
        self.assertEqual(run_program('add'), 1)


class TestCreate(unittest.TestCase):
    """Tests the creation of a new file store on disk.
    """
    def test_create(self):
        with temp_dir() as d:
            self.assertEqual(run_program(d, 'create'), 0)
            self.assertTrue(os.path.isfile(os.path.join(d, 'database')))

    def test_create_nonempty(self):
        with temp_dir() as d:
            with open(os.path.join(d, 'somefile'), 'wb') as fp:
                fp.write(b"I'm not empty\n")
            self.assertEqual(run_program(d, 'create'), 3)


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
        out = []
        self.assertEqual(run_program(self.path, 'query', out=out), 0)
        self.assertEqual(out, [])

    def test_putfile(self):
        out = []
        self.assertEqual(
                run_program(self.path, 'add', self.t('file1.bin'), 'a=b',
                            out=out),
                0)
        h1 = 'fce92fa2647153f7d696a3c1884d732290273102'
        self.assertEqual(out, [h1])
        self.assertTrue(os.path.isfile(os.path.join(
                self.path,
                'objects',
                'fc',
                'e92fa2647153f7d696a3c1884d732290273102')))
        self.assertEqual(
                self.store.get(h1).metadata,
                {'hash': h1, 'a': 'b'})

    def test_wrongpath(self):
        self.assertEqual(run_program(self.path, 'add', 'nonexistentpath-fa'),
                         1)

    def test_query(self):
        self.store.add_file(self.t('file1.bin'), {'tag': 'testfile', 'test': 1})
        self.store.add_file(self.t('file2.bin'), {'tag': 'other', 'test': 2})

        def r(*args):
            out = []
            self.assertEqual(run_program(self.path, *args, out=out), 0)
            return out

        h1 = 'fce92fa2647153f7d696a3c1884d732290273102'
        h2 = 'de0ccf54a9c1de0d9fdbf23f71a64762448057d0'

        out = r('query', 'tag=testfile')
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0], h1)
        m1 = '\t%s\t%s' % ('test', '1')
        m2 = '\t%s\t%s' % ('tag', 'testfile')
        self.assertTrue(out[1:] in ([m1, m2], [m2, m1]))

        out = r('query', '-d')
        self.assertEqual(eval('\n'.join(out)), {
                h1: {'tag': 'testfile', 'test': 1},
                h2: {'tag': 'other', 'test': 2},
            })

    # TODO : print


# TODO : parse_query_metadata(), parse_new_metadata()
