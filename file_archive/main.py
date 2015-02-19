import locale
import os
import sys
import tempfile
import warnings

from file_archive import FileStore, copy_file, BufferedReader
from file_archive.compat import int_types, unicode_type, quote_str
from file_archive.errors import UsageWarning
from file_archive.trans import _


def parse_query_metadata(args):
    """Parses a list of key=value arguments or a hash value.

    Returns (hash:str, metadata:dict)
    """
    if len(args) == 1 and '=' not in args[0]:
        return args[0], None
    else:
        metadata = {}
        for a in args:
            k = a.split('=', 1)
            if len(k) != 2:
                sys.stderr.write(_(u"Metadata should have format key=value, "
                                   u"key=type:value (eg. age=int:23) or "
                                   u"key=type:req (eg. age=int:>21)\n"))
                sys.exit(1)
            k, v = k
            if ':' in v:
                t, v = v.split(':', 1)
                if t == 'int':
                    if v[0] == '>':
                        req, v = 'gt', v[1:]
                    elif v[0] == '<':
                        req, v = 'lt', v[1:]
                    else:
                        req = 'equal'
                    v = int(v)
                elif t == 'str':
                    req = 'equal'
                else:
                    sys.stderr.write(_(u"Metadata has unknown type '{t}'! "
                                       u"Only 'str' and 'int' are supported.\n"
                                       u"If you meant a string with a ':', "
                                       u"use 'str:mystring'", t=t))
                    sys.exit(1)
            else:
                t = 'str'
                req = 'equal'
            if t == 'str' and isinstance(v, bytes):
                v = v.decode(locale.getpreferredencoding())
            if k in metadata:
                if t != metadata[k]['type']:
                    sys.stderr.write(_(u"Differing types for conditions on "
                                       u"key {k}: {t1}, {t2}\n",
                                       k=k, t1=metadata[k]['type'], t2=t))
                    sys.exit(1)
                if req in metadata[k]:
                    sys.stderr.write(_(u"Multiple conditions {cond} on key "
                                       u"{k}\n",
                                       cond=req, k=k))
                    sys.exit(1)
                metadata[k][req] = v
            else:
                metadata[k] = {'type': t, req: v}
        return None, metadata


def parse_new_metadata(args):
    """Parses a list of key=value or key=type:value arguments.
    """
    metadata = {}
    for a in args:
        k = a.split('=', 1)
        if len(k) != 2:
            sys.stderr.write(_(u"Metadata should have format key=value or "
                               u"key=type:value (eg. age=int:23)\n"))
            sys.exit(1)
        k, v = k
        if ':' in v:
            t, v = v.split(':', 1)
        else:
            t = 'str'
        if k in metadata:
            sys.stderr.write("Multiple values for key %s\n" % k)
            sys.exit(1)
        if t == 'int':
            v = int(v)
        elif t == 'str':
            if isinstance(v, bytes):
                v = v.decode(locale.getpreferredencoding())
        else:
            sys.stderr.write(_(u"Metadata has unknown type '{t}'! Only 'str' "
                               u"and 'int' are supported.\n"
                               u"If you meant a string with a ':', use "
                               u"'str:mystring'", t=t))
            sys.exit(1)
        metadata[k] = {'type': t, 'value': v}
    return metadata


def cmd_add(store, args):
    """Add command.

    add <filename> [key1=value1] [...]
    """
    if not args:
        sys.stderr.write(_(u"Missing filename\n"))
        sys.exit(1)
    filename = args[0]
    if not os.path.exists(filename):
        sys.stderr.write(_(u"Path does not exist: {path}\n", path=filename))
        sys.exit(1)
    metadata = parse_new_metadata(args[1:])
    if os.path.isdir(filename):
        entry = store.add_directory(filename, metadata)
    else:
        entry = store.add_file(filename, metadata)
    sys.stdout.write('%s\n' % entry['hash'])


def cmd_write(store, args):
    """Write command.

    write [key1=value1] [...]
    """
    metadata = parse_new_metadata(args)
    fd, filename = tempfile.mkstemp()
    os.close(fd)
    try:
        copy_file(sys.stdin, filename)
        entry = store.add_file(filename, metadata)
    finally:
        os.remove(filename)
    sys.stdout.write('%s\n' % entry['hash'])


def cmd_query(store, args):
    """Query command.

    query [-d] [-t] [key1=value1] [...]
    """
    pydict = False
    types = False
    while args and args[0][0] == '-':
        if args[0] == '-d':
            pydict = True
        elif args[0] == '-t':
            types = True
        elif args[0] == '--':
            del args[0]
            break
        else:
            sys.stderr.write(_(u"Unknown option: {opt}\n", opt=args[0]))
            sys.exit(1)
        del args[0]
    h, metadata = parse_query_metadata(args)
    if h is not None:
        entries = [store.get(h)]
    else:
        entries = store.query(metadata)
    if not pydict:
        for entry in entries:
            sys.stdout.write("%s\n" % entry['hash'])
            for k, v in entry.metadata.items():
                if k == 'hash':
                    continue
                if types:
                    if isinstance(v, int_types):
                        v = 'int:%d' % v
                    else:  # isinstance(v, string_types):
                        v = 'str:%s' % v
                sys.stdout.write("\t%s\t%s\n" % (k, v))
    else:
        sys.stdout.write('{\n')
        for entry in entries:
            sys.stdout.write("    '%s': {\n" % entry['hash'])
            for k, v in entry.metadata.items():
                if k == 'hash':
                    continue
                if types:
                    if isinstance(v, int_types):
                        v = "{'type': 'int', 'value': %d}" % v
                    else:  # isinstance(v, string_types):
                        assert isinstance(v, unicode_type)
                        v = "{'type': 'str', 'value': u%s}" % quote_str(v)
                else:
                    if isinstance(v, int_types):
                        v = '%d' % v
                    else:  # isinstance(v, string_types):
                        assert isinstance(v, unicode_type)
                        v = "u%s" % quote_str(v)
                k = quote_str(k)
                sys.stdout.write("        u%s: %s,\n" % (k, v))
            sys.stdout.write('    },\n')
        sys.stdout.write('}\n')


def cmd_print(store, args):
    """Print command.

    print [-m] [-t] <filehash> [...]
    print [-m] [-t] [key1=value1] [...]
    """
    meta = False
    types = False
    while args and args[0][0] == '-':
        if args[0] == '-m':
            meta = True
        elif args[0] == '-t':
            types = True
        elif args[0] == '--':
            del args[0]
            break
        else:
            sys.stderr.write(_(u"Unknown option: {opt}\n", opt=args[0]))
            sys.exit(1)
        del args[0]
    h, metadata = parse_query_metadata(args)
    if h is not None:
        try:
            entry = store.get(h)
        except KeyError:
            sys.stderr.write(_(u"Hash not found\n"))
            sys.exit(2)
    else:
        entries = store.query(metadata)
        try:
            entry = next(entries)
        except StopIteration:
            sys.stderr.write(_(u"No match found\n"))
            sys.exit(2)
        try:
            next(entries)
        except StopIteration:
            pass
        else:
            sys.stderr.write(_(u"Warning: more matching files exist\n"))
    if meta:
        for k, v in entry.metadata.items():
            if k == 'hash':
                continue
            if types:
                if isinstance(v, int_types):
                    v = 'int:%d' % v
                else:  # isinstance(v, string_types):
                    v = 'str:%s' % v
            sys.stdout.write("%s\t%s\n" % (k, v))
    else:
        if os.path.isdir(entry.filename):
            sys.stderr.write(_(u"Error: match found but is a directory\n"))
            sys.exit(2)
        fp = entry.open()
        try:
            for chunk in BufferedReader(fp):
                sys.stdout.write(chunk)
        finally:
            fp.close()


def cmd_remove(store, args):
    """Remove command.

    remove [-f] <filehash>
    remove [-f] <key1=value1> [...]
    """
    if args and args[0] == '-f':
        del args[0]
        force = True
    else:
        force = False
    h, metadata = parse_query_metadata(args)
    if h is not None:
        store.remove(h)
    else:
        entries = store.query(metadata)
        if not args and not force:
            nb = sum(1 for e in entries)
            if nb:
                sys.stderr.write(_(
                        u"Error: not removing files unconditionally unless -f "
                        u"is given\n"
                        u"(command would have removed {nb} files)\n",
                        nb=nb))
                sys.exit(1)
        for e in entries:
            store.remove(e)


def cmd_verify(store, args):
    """Verify command.

    This command accepts no argument.
    """
    if args:
        sys.stderr.write(_(u"verify command accepts no argument\n"))
        sys.exit(1)
    store.verify()


def cmd_view(store, args):
    if args:
        sys.stderr.write(_(u"view command accepts no argument\n"))
        sys.exit(1)
    from .viewer import run_viewer
    run_viewer(store)


commands = {
        'add': cmd_add,
        'write': cmd_write,
        'query': cmd_query,
        'print': cmd_print,
        'remove': cmd_remove,
        'verify': cmd_verify,
        'view': cmd_view}


def main(args):
    warnings.filterwarnings('always', category=UsageWarning)

    usage = _(
            u"usage: {bin} <store> create\n"
            u"   or: {bin} <store> add <filename> [key1=value1] [...]\n"
            u"   or: {bin} <store> write [key1=value1] [...]\n"
            u"   or: {bin} <store> query [-d] [-t] [key1=value1] [...]\n"
            u"   or: {bin} <store> print [-m] [-t] <filehash> [...]\n"
            u"   or: {bin} <store> print [-m] [-t] [key1=value1] [...]\n"
            u"   or: {bin} <store> remove [-f] <filehash>\n"
            u"   or: {bin} <store> remove [-f] <key1=value1> [...]\n"
            u"   or: {bin} <store> verify\n"
            u"   or: {bin} <store> view\n",
            bin='file_archive')

    if len(args) < 2:
        sys.stderr.write(usage)
        sys.exit(1)

    store = args[0]
    command = args[1]

    if command == 'create':
        try:
            FileStore.create_store(store)
        except Exception as e:
            sys.stderr.write(_(u"Can't create store: {err}\n", err=e.args[0]))
            sys.exit(3)
        sys.exit(0)

    try:
        store = FileStore(store)
    except Exception as e:
        sys.stderr.write(_(u"Invalid store: {err}\n", err=e.args[0]))
        sys.exit(3)

    try:
        try:
            func = commands[command]
        except KeyError:
            sys.stderr.write(usage)
            sys.exit(1)
        try:
            func(store, args[2:])
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(3)
    finally:
        store.close()

    sys.exit(0)
