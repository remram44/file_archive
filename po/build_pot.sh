#!/bin/sh

DIR=$(dirname $0)/..

exec xgettext \
    --language=Python \
    --keyword=_ \
    --keyword=_n:1,2 \
    --output=$DIR/po/file_archive.pot \
    $(find $DIR/file_archive -name '*.py')
