from __future__ import division, unicode_literals

import gettext
import locale
import pkg_resources


__all__ = ['setup_translation', '_', '_n']


# Entry points should be using:
#   locale.setlocale(locale.LC_ALL, '')
#   file_archive.trans.setup_translation()


if str == bytes:
    string_types = basestring
else:
    string_types = str


trans = gettext.NullTranslations()


def setup_translation(languages=None):
    global trans

    if languages is None:
        languages = []
    elif isinstance(languages, string_types):
        languages = [languages]

    d = pkg_resources.resource_filename('file_archive', 'l10n')

    lang = locale.getlocale()[0]
    if lang is not None:
        languages.append(lang)
    trans = gettext.translation('file_archive', d, languages, fallback=True)


if hasattr(trans, 'ugettext'):
    def _(*args, **kwargs):
        tr = trans.ugettext(*args)
        if kwargs:
            tr = tr.format(**kwargs)
        return tr

    def _n(singular, plural, n, **kwargs):
        tr = trans.ungettext(singular, plural, n)
        if kwargs:
            tr = tr.format(**kwargs)
        return tr
else:
    # ugettext was removed from Python 3
    def _(*args, **kwargs):
        tr = trans.gettext(*args)
        if kwargs:
            tr = tr.format(**kwargs)
        return tr

    def _n(singular, plural, n, **kwargs):
        tr = trans.ngettext(singular, plural, n)
        if kwargs:
            tr = tr.format(**kwargs)
        return tr
