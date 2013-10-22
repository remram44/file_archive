import os
import sys
try:
    from file_archive.entry_point import entry_point
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from file_archive.entry_point import entry_point


if __name__ == '__main__':
    entry_point()
