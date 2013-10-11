import contextlib
import os
import sys
import tempfile
import shutil
try:
    import unittest2 as unittest
except ImportError:
    import unittest

from file_archive import FileStore
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


@contextlib.contextmanager
def catch_errorexit():
    err = StringIO()
    old_stderr, sys.stderr = sys.stderr, err
    ret = [None]
    try:
        yield ret
    except SystemExit as e:
        ret[0] = e.code
    else:
        ret[0] = None
    finally:
        sys.stderr = old_stderr


class TestParseQuery(unittest.TestCase):
    def test_hash(self):
        h = '22596363b3de40b06f981fb85d82312e8c0ed511'
        self.assertEqual(file_archive.main.parse_query_metadata([h]),
                         (h, None))

        with catch_errorexit() as e:
            file_archive.main.parse_query_metadata([h, 'tag=file'])
        self.assertEqual(e[0], 1)

    def test_strs(self):
        strs = ['type=a file',
                'month=str:october',
                'time=str:11:20']
        dct = {'type': {'type': 'str', 'equal': u'a file'},
               'month': {'type': 'str', 'equal': u'october'},
               'time': {'type': 'str', 'equal': u'11:20'}}
        self.assertEqual(file_archive.main.parse_query_metadata(strs),
                         (None, dct))

    def test_ints(self):
        strs = ['year=int:2013', 'age=int:>21', 'nb=int:>2', 'nb=int:<4']
        dct = {'year': {'type': 'int', 'equal': 2013},
               'age': {'type': 'int', 'gt': 21},
               'nb': {'type': 'int', 'gt': 2, 'lt': 4}}
        self.assertEqual(file_archive.main.parse_query_metadata(strs),
                         (None, dct))

    def test_errors(self):
        def error1(*args):
            with catch_errorexit() as e:
                file_archive.main.parse_query_metadata(args)
            self.assertEqual(e[0], 1)

        error1('k=int:<2', 'k=int:<3')
        error1('k=str:age', 'k=int:23')
        error1('k=str:A', 'k=str:B')
        error1('k=burger:A')


class TestParseNewData(unittest.TestCase):
    def test_data(self):
        self.assertEqual(file_archive.main.parse_new_metadata(
                ['type=a file', 'month=str:october',
                 'time=str:11:40', 'year=int:2013']),
                {'type': {'type': 'str', 'value': u'a file'},
                 'month': {'type': 'str', 'value': u'october'},
                 'time': {'type': 'str', 'value': u'11:40'},
                 'year': {'type': 'int', 'value': 2013}})

    def test_errors(self):
        def error1(*args):
            with catch_errorexit() as e:
                file_archive.main.parse_query_metadata(args)
            self.assertEqual(e[0], 1)

        error1('a', 'b')
        error1('k=burger:A')
        error1('k=str:A', 'k=int:7')
