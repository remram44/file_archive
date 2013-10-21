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


def _(*args):
    return trans.ugettext(*args)

def _n(singular, plural, n):
    return trans.ungettext(singular, plural, n)
