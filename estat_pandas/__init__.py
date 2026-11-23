# estat/__init__.py
from .reader import EStatAPIError, EStatReader, DataReader, search

__version__ = "0.1.0"

__all__ = ["EStatAPIError", "EStatReader", "DataReader", "search"]