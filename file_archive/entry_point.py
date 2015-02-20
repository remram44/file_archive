from __future__ import division, unicode_literals

import codecs
import locale
import sys

from file_archive.main import main
from file_archive.trans import setup_translation


def entry_point():
    # Locale
    locale.setlocale(locale.LC_ALL, str(''))

    # Encoding for output streams
    if str == bytes:
        writer = codecs.getwriter(locale.getpreferredencoding())
        sys.stdout = writer(sys.stdout)
        sys.stderr = writer(sys.stderr)

    # Load gettext translation catalog
    setup_translation()

    main(sys.argv[1:])
