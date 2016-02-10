#!/bin/sh

cd "$(dirname "$0")/.."

exec xgettext \
    --language=Python \
    --keyword=_ \
    --keyword=_n:1,2 \
    --output=po/file_archive.pot \
    $(find file_archive -name '*.py')
