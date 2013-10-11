try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


description = """
file_archive is a file archiving system. You submit it files with a set of
metadata, as key-value pairs, and it allows you to later retrieve the files
that match conditions on these metadata.

It uses a flat file-store where files are stored under their 40 characters SHA1
hash, and a SQLite3 database for the metadata.

Its purpose is to be used as a persistent file store for the VisTrails workflow
and provenance management system: http://www.vistrails.org/
"""
setup(name='file_archive',
      version='0.3',
      packages=['file_archive'],
      entry_points={
          'console_scripts': ['file_archive = file_archive.main:main']},
      description='A file store with searchable metadata',
      author="NYU-Poly",
      author_email='vistrails-dev@vistrails.org',
      url='http://github.com/remram44/file_archive',
      long_description=description,
      license='Modified BSD License',
      keywords=['file', 'archive', 'metadata'],
      classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Environment :: Console',
        'Operating System :: OS Independent',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Topic :: System :: Archiving'],
      requires=['tdparser (>=1.1.4)'])
