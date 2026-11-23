import os
import unittest
from pathlib import Path

import pandas as pd

from estat_pandas import load


def _load_local_api_key():
    if os.environ.get("ESTAT_APP_ID"):
        return
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "ESTAT_APP_ID":
            os.environ["ESTAT_APP_ID"] = value.strip().strip("\"'")
            return


@unittest.skipUnless(
    os.environ.get("ESTAT_LIVE_LINK_CHECK") == "1",
    "set ESTAT_LIVE_LINK_CHECK=1 to run live e-Stat link checks",
)
class LiveLinkTests(unittest.TestCase):
    def test_latest_unemployment_workbook_link_is_available(self):
        _load_local_api_key()
        self.assertTrue(
            os.environ.get("ESTAT_APP_ID"),
            "set ESTAT_APP_ID or add it to the local .env file",
        )

        frame = load(
            "JPN_UNEMPLOYMENT_RATE_MONTHLY_SA",
            start="2026-09-01",
            end="2026-09-01",
        )

        self.assertEqual(frame["DATE"].tolist(), [pd.Timestamp("2026-09-01")])
        self.assertTrue(frame["value"].notna().all())
        self.assertEqual(
            frame["seasonal_adjustment"].unique().tolist(),
            ["seasonally_adjusted"],
        )


if __name__ == "__main__":
    unittest.main()
