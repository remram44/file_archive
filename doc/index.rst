.. _index:

file_archive: A file store with searchable metadata
===================================================

About
-----

file_archive can be used either as a command-line tool, to create, change or
query a file store, or as a Python library. It is intended to keep simulation
results or other large number of similar objects, and is used as the back-end
for `VisTrails workflow management and provenance system
<http://www.vistrails.org/>`_. 

A file store is simply a directory with an ``objects`` subdirectory, containing
the actual files, and a ``database`` file, an SQLite3 database containing the
metadata.

The metadata simply consists of key=value pairs. You give the system these
pairs when you add it, and you can then do query on the entire filestore to
find the files matching a given conditions. Example::

   $ file_archive ../mystore add /tmp/simresults model=weather2 cluster=poly
   0f72c656ac0997fcab8f6590f71c57fc1a767508
   $ file_archive ../mystore query model=weather2
   a77a813e049b1f05afd614fe4b8e11e59fb65b99
           cluster: "poly-old"
           model: "weather2"
   0f72c656ac0997fcab8f6590f71c57fc1a767508
           cluster: "poly"
           model: "weather2"

Command-line usage
------------------

Using it as a command-line tool is pretty easy; typing ``file_archive`` (or
``python file_archive`` if you did not install it system-wide) will give you
the following quick reference::

   usage: file_archive <store> create
      or: file_archive <store> add <filename> [key1=value1] [...]
      or: file_archive <store> query [key1=value1] [...]
      or: file_archive <store> print <filehash> [...]
      or: file_archive <store> print [key1=value1] [...]
      or: file_archive <store> remove <filehash>
      or: file_archive <store> remove <key1=value1> [...]
      or: file_archive <store> verify

Using file_archive as a library
-------------------------------

File :class:`~file_archive.FileStore` class can be used to add, remove and
query from a store.

.. autoclass:: file_archive.FileStore
   :members:
