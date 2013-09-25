import os
import sys
try:
    import file_archive
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    import file_archive


if __name__ == '__main__':
    from file_archive.main import main
    main()
