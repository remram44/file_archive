import logging
import os
import sys
import warnings

from file_archive import FileStore, CHUNKSIZE


def parse_metadata(args, first_can_be_hash):
    """Parses a list of key=value arguments.

    If first_can_be_hash is True, it will accept a single hash instead. In this
    case the return format changes, and (hash:str, metadata:dict) gets returned
    instead of just metadata.
    """
    if len(args) == 1 and first_can_be_hash and '=' not in args[0]:
        return args[0], None
    else:
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
        if first_can_be_hash:
            return None, metadata
        else:
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
    metadata = parse_metadata(args[1:], False)
    if os.path.isdir(filename):
        h = store.add_directory(filename, metadata)
    else:
        h = store.add_file(filename, metadata)
    sys.stdout.write('%s\n' % h)


def cmd_query(store, args):
    """Query command.

    query [key1=value1] [...]
    """
    metadata = parse_metadata(args, False)
    entries = store.query(metadata)
    for entry in entries:
        sys.stdout.write("%s\n" % entry['hash'])
        for k, v in entry.metadata.iteritems():
            if k == 'hash':
                continue
            if isinstance(v, unicode):
                v = '"%s"' % v.replace("\\", "\\\\").replace('"', '\\"')
            sys.stdout.write("\t%s: %s\n" % (k, v))


def cmd_print(store, args):
    """Print command.

    print <filehash> [...]
    print [key1=value1] [...]
    """
    h, metadata = parse_metadata(args, True)
    if h is None:
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
    else:
        try:
            entry = store.get(h)
        except:
            sys.stderr.write("Hash not found\n")
            sys.exit(2)
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

    remove <filehash>
    remove <key1=value1> [...]
    """
    h, metadata = parse_metadata(args, True)
    if h:
        store.remove(h)
    else:
        for h in store.query(metadata):
            store.remove(h)


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
            "   or: {bin} <store> query [key1=value1] [...]\n"
            "   or: {bin} <store> print <filehash> [...]\n"
            "   or: {bin} <store> print [key1=value1] [...]\n"
            "   or: {bin} <store> remove <filehash>\n"
            "   or: {bin} <store> remove <key1=value1> [...]\n"
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
