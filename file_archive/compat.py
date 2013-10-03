from abc import ABCMeta
import hashlib


try:
    basestring
except NameError:
    basestring = str
else:
    basestring = basestring

try:
    long
except NameError:
    baseint = int
else:
    class baseint:
        __metaclass__ = ABCMeta
    baseint.register(int)
    baseint.register(long)


class sha1(object):
    def __init__(self, arg=b''):
        self._hash = hashlib.sha1()
        if arg:
            self.update(arg)

    def update(self, arg):
        if not isinstance(arg, bytes):
            arg = arg.encode('ascii')
        self._hash.update(arg)

    def hexdigest(self):
        return self._hash.hexdigest()
