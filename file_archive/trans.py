import gettext
import locale
import pkg_resources


# Entry points should be using:
#locale.setlocale(locale.LC_ALL, '')


d = pkg_resources.resource_filename('file_archive', 'l10n')

languages = []
lang = locale.getlocale()[0]
if lang is not None:
    languages.append(lang)
trans = gettext.translation('file_archive', d, languages, fallback=True)


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
