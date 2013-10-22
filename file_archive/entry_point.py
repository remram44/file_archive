import locale
import sys

from file_archive.main import main
from file_archive.trans import setup_translation


def entry_point():
    locale.setlocale(locale.LC_ALL, '')
    setup_translation()
    main(sys.argv[1:])
