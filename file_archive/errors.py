class Error(Exception):
    """Base class for this package's exceptions.
    """


class InvalidStore(ValueError, Error):
    """Indicates that the store at the given path is corrupted or not a store.
    """


class CreationError(IOError, Error):
    """Failed to create a new store at the given path.
    """


class UsageWarning(UserWarning):
    """Something unsafe was requested and carried out.
    """
