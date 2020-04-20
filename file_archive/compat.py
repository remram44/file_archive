"""Python 2/3 compatibility symbols.

isinstance() checks:
 * Use string_types instead of 2's basestring
 * Use int_types instead of 3's int

sha1:
 * Silently accepts unicode so long as it's ASCII

BytesIO, StringIO
"""

from __future__ import division, unicode_literals

import hashlib
import sys


__all__ = ['PY3', 'string_types', 'int_types', 'sha1', 'unicode_type',
           'StringIO', 'BytesIO']


PY3 = sys.version_info >= (3, 0)


if not PY3:
    string_types = basestring  # noqa: F821
    int_types = int, long  # noqa: F821
    unicode_type = unicode  # noqa: F821

    from StringIO import StringIO
    BytesIO = StringIO
else:
    string_types = str
    int_types = int
    unicode_type = str

    from io import StringIO, BytesIO


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
