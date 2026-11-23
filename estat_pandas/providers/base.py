from __future__ import annotations

from typing import Protocol

import pandas as pd

from ..catalog import DatasetSpec


class Provider(Protocol):
    def fetch(
        self,
        dataset: DatasetSpec,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        """Return provider data with DATE and value columns."""

