#!/bin/sh

DIR=$(dirname $0)/..

exec xgettext \
    --language=Python \
    --keyword=_ \
    --output=$DIR/po/file_archive.pot \
    $(find $DIR/file_archive -name '*.py')
