class SourceRegistryError(Exception):
    """Base exception for SourceRegistry."""


class SourceNotFoundError(SourceRegistryError):
    """Raised when a source entry cannot be resolved."""


class DuplicateSourceError(SourceRegistryError):
    """Raised when duplicate source names are provided."""


class GitOperationError(SourceRegistryError):
    """Raised when a git operation fails."""


class RegistryLoadError(SourceRegistryError):
    """Raised when loading source registry data fails."""
