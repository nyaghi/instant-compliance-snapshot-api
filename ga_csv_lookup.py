from __future__ import annotations

import os
from pathlib import Path

from utah_csv_lookup import REQUIRED_COLUMNS, UtahCsvLookup


GA_CSV_PATH_ENV = "CE_GA_STATUS_CSV_PATH"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_GA_CSV_PATH = BASE_DIR / "state_data" / "ga" / "GA_STATUS_LIST_copy_paste_batches.csv"


class GaCsvLookup(UtahCsvLookup):
    def __init__(self, csv_path: str | Path | None = None):
        configured_path = csv_path or os.environ.get(GA_CSV_PATH_ENV) or DEFAULT_GA_CSV_PATH
        super().__init__(configured_path, state_name="Georgia", error_prefix="GA")

GA_CSV_LOOKUP = GaCsvLookup()
