import logging
import os
import sys
import warnings

from file_archive import FileStore, CHUNKSIZE
from file_archive.compat import int_types, unicode_type, quote_str


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
                sys.stderr.write("Metadata should have format key=value, "
                                 "key=type:value (eg. age=int:23) or"
                                 "key=type:req (eg. age=int:>21\n")
                sys.exit(1)
            k, v = k
            if ':' in v:
                t, v = v.split(':', 1)
                if t == 'int':
                    v = int(v)
                elif t != 'str':
                    sys.stderr.write("Metadata has unknown type '%s'! Only "
                                     "'str' and 'int' are supported.\n"
                                     "If you meant a string with a ':', use "
                                     "'str:mystring'" % t)
                metadata[k] = {'type': t, 'equal': v}
            else:
                metadata[k] = v
        return None, metadata


def parse_new_metadata(args):
    """Parses a list of key=value or key=type:value arguments.
    """
    metadata = {}
    for a in args:
        k = a.split('=', 1)
        if len(k) != 2:
            sys.stderr.write("Metadata should have format key=value or "
                             "key=type:value (eg. age=int:23)\n")
            sys.exit(1)
        k, v = k
        if ':' in v:
            t, v = v.split(':', 1)
            metadata[k] = {'type': t, 'value': v}
        else:
            metadata[k] = v
    return metadata


def cmd_add(store, args):
    """Add command.

    add <filename> [key1=value1] [...]
    """
    if len(sys.argv) < 4:
        sys.stderr.write("Missing filename\n")
        sys.exit(1)
    filename = args[0]
    if not os.path.exists(filename):
        sys.stderr.write("Path does not exist: %s\n" % filename)
        sys.exit(1)
    metadata = parse_new_metadata(args[1:])
    if os.path.isdir(filename):
        entry = store.add_directory(filename, metadata)
    else:
        entry = store.add_file(filename, metadata)
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
            sys.stderr.write("Unknown option: %s\n", args[0])
            sys.exit(1)
        del args[0]
    h, metadata = parse_query_metadata(args)
    if h is not None:
        sys.stderr.write("query doesn't take a hash but conditions\n")
        sys.exit(1)
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
                    else: # isinstance(v, string_types):
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
                    else: # isinstance(v, string_types)
                        assert isinstance(v, unicode_type)
                        v = "{'type': 'str', 'value': u%s}" % quote_str(v)
                else:
                    if isinstance(v, int_types):
                        v = '%d' % v
                    else: # isinstance(v, string_types)
                        assert isinstance(v, unicode_type)
                        v = "u%s" % quote_str(v)
                k = quote_str(k)
                sys.stdout.write("        u'%s': %s,\n" % (k, v))
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
            sys.stderr.write("Unknown option: %s\n", args[0])
            sys.exit(1)
        del args[0]
    h, metadata = parse_query_metadata(args)
    if h is not None:
        try:
            entry = store.get(h)
        except:
            sys.stderr.write("Hash not found\n")
            sys.exit(2)
    else:
        entries = store.query(metadata)
        try:
            entry = next(entries)
        except StopIteration:
            sys.stderr.write("No match found\n")
            sys.exit(2)
        try:
            next(entries)
        except StopIteration:
            pass
        else:
            sys.stderr.write("Warning: more matching files exist\n")
    if meta:
        for k, v in entry.metadata.items():
            if k == 'hash':
                continue
            if types:
                if isinstance(v, int_types):
                    v = 'int:%d' % v
                else: # isinstance(v, string_types):
                    v = 'str:%s' % v
            sys.stdout.write("%s\t%s\n" % (k, v))
    else:
        if os.path.isdir(entry.filename):
            sys.stderr.write("Error: match found but is a directory\n")
            sys.exit(2)
        fp = entry.open()
        try:
            chunk = fp.read(CHUNKSIZE)
            while chunk:
                sys.stdout.write(chunk)
                chunk = fp.read(CHUNKSIZE)
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
                sys.stderr.write("Error: not removing files unconditionally "
                                 "unless -f is given\n"
                                 "(command would have removed %d files)\n" % (
                                 nb))
                sys.exit(1)
        for e in entries:
            store.remove(e)


def cmd_verify(store, args):
    """Verify command.

    This command accepts no argument.
    """
    if args:
        sys.stderr.write("verify command accepts no argument\n")
        sys.exit(1)
    store.verify()


commands = {
        'add': cmd_add,
        'query': cmd_query,
        'print': cmd_print,
        'remove': cmd_remove,
        'verify': cmd_verify,
    }


def main():
    logging.basicConfig()
    logging.captureWarnings(True)
    warnings.simplefilter('once')

    usage = (
            "usage: {bin} <store> create\n"
            "   or: {bin} <store> add <filename> [key1=value1] [...]\n"
            "   or: {bin} <store> query [-d] [-t] [key1=value1] [...]\n"
            "   or: {bin} <store> print [-m] [-t] <filehash> [...]\n"
            "   or: {bin} <store> print [-m] [-t] [key1=value1] [...]\n"
            "   or: {bin} <store> remove [-f] <filehash>\n"
            "   or: {bin} <store> remove [-f] <key1=value1> [...]\n"
            "   or: {bin} <store> verify\n".format(
            bin='file_archive'))

    if len(sys.argv) < 3:
        sys.stderr.write(usage)
        sys.exit(1)

    store = sys.argv[1]
    command = sys.argv[2]

    if command == 'create':
        FileStore.create_store(store)
        sys.exit(0)

    store = FileStore(store)

    try:
        try:
            func = commands[command]
        except KeyError:
            sys.stderr.write(usage)
            sys.exit(1)
        func(store, sys.argv[3:])
    finally:
        store.close()

    sys.exit(0)
