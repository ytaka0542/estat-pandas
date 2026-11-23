class AcquisitionError(RuntimeError):
    """Base error for catalog, provider, and data validation failures."""


class CatalogError(AcquisitionError, ValueError):
    """Raised when the dataset catalog is invalid."""


class DatasetNotFoundError(AcquisitionError, KeyError):
    """Raised when a dataset key is not registered."""


class ProviderError(AcquisitionError):
    """Raised when a provider cannot return a valid response."""


class DataValidationError(AcquisitionError, ValueError):
    """Raised when returned observations violate the shared data contract."""


class NoDataError(AcquisitionError):
    """Raised when a dataset has no observations in the requested period."""
