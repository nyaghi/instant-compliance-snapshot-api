from __future__ import annotations

import codecs
import csv
import io
import os
import re
import unicodedata
from collections import defaultdict
from pathlib import Path


UTAH_CSV_PATH_ENV = "CE_UTAH_STATUS_CSV_PATH"
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_UTAH_CSV_PATH = BASE_DIR / "state_data" / "utah" / "UTAH_STATUS_LIST_copy_paste_batches.csv"
REQUIRED_COLUMNS = (
    "DATE CHECKED",
    "ORG NAME",
    "EIN",
    "STATUS",
    "EXPIRATION DATE",
)


def normalize_ein(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def valid_normalized_ein(value: str) -> str:
    normalized = normalize_ein(value)
    return normalized if len(normalized) == 9 else ""


def normalize_organization_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold().strip()
    normalized = "".join(
        " " if unicodedata.category(character).startswith("P") or character in "&+" else character
        for character in normalized
    )
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def decode_csv_bytes(raw: bytes) -> tuple[str, str]:
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"


class UtahCsvLookup:
    def __init__(
        self,
        csv_path: str | Path | None = None,
        *,
        state_name: str = "Utah",
        error_prefix: str = "UTAH",
    ):
        configured_path = csv_path or os.environ.get(UTAH_CSV_PATH_ENV) or DEFAULT_UTAH_CSV_PATH
        self.csv_path = Path(configured_path).expanduser()
        self.state_name = state_name
        self.error_prefix = error_prefix
        self.encoding = ""
        self.headers: list[str] = []
        self.rows: list[dict[str, str]] = []
        self.ein_index: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.name_index: dict[str, list[dict[str, str]]] = defaultdict(list)
        self.error_code = ""
        self.error = ""
        self._load()

    def _load(self) -> None:
        try:
            raw = self.csv_path.read_bytes()
        except FileNotFoundError:
            self.error_code = f"{self.error_prefix}_CSV_FILE_NOT_FOUND"
            self.error = (
                f"{self.state_name} status CSV not found: {self.csv_path}."
            )
            return
        except OSError as exc:
            self.error_code = f"{self.error_prefix}_CSV_READ_ERROR"
            self.error = f"{self.state_name} status CSV could not be read at {self.csv_path}: {exc}"
            return

        try:
            text, self.encoding = decode_csv_bytes(raw)
        except UnicodeError as exc:
            self.error_code = f"{self.error_prefix}_CSV_ENCODING_ERROR"
            self.error = f"{self.state_name} status CSV encoding could not be decoded safely at {self.csv_path}: {exc}"
            return

        reader = csv.DictReader(io.StringIO(text, newline=""))
        self.headers = list(reader.fieldnames or [])
        missing = [column for column in REQUIRED_COLUMNS if column not in self.headers]
        if missing:
            self.error_code = f"{self.error_prefix}_CSV_MISSING_COLUMNS"
            self.error = (
                f"{self.state_name} status CSV is missing required columns: "
                f"{', '.join(missing)}. Found columns: {', '.join(self.headers) or '(none)'}."
            )
            return

        for source_row in reader:
            row = {column: source_row.get(column) or "" for column in self.headers}
            if not any(row.values()):
                continue
            self.rows.append(row)
            ein_key = valid_normalized_ein(row["EIN"])
            if ein_key:
                self.ein_index[ein_key].append(row)
            name_key = normalize_organization_name(row["ORG NAME"])
            if name_key:
                self.name_index[name_key].append(row)

    @staticmethod
    def _matched(row: dict[str, str], matched_by: str) -> dict:
        return {
            "outcome": "matched",
            "matched_by": matched_by,
            "organization_name": row["ORG NAME"],
            "ein": row["EIN"],
            "status": row["STATUS"],
            "expiration_date": row["EXPIRATION DATE"],
            "last_date_checked": row["DATE CHECKED"],
            "row": dict(row),
        }

    @staticmethod
    def _ambiguous(matched_by: str, candidates: list[dict[str, str]]) -> dict:
        return {
            "outcome": "ambiguous",
            "matched_by": matched_by,
            "candidate_count": len(candidates),
            "candidates": [
                {"organization_name": row["ORG NAME"], "ein": row["EIN"]}
                for row in candidates
            ],
        }

    def lookup(self, organization_name: str = "", ein: str = "") -> dict:
        if self.error:
            return {
                "outcome": "error",
                "error_code": self.error_code,
                "error": self.error,
            }

        ein_key = valid_normalized_ein(ein)
        if ein_key:
            candidates = self.ein_index.get(ein_key, [])
            if len(candidates) == 1:
                return self._matched(candidates[0], "ein")
            if len(candidates) > 1:
                return self._ambiguous("ein", candidates)

        name_key = normalize_organization_name(organization_name)
        if name_key:
            candidates = self.name_index.get(name_key, [])
            if len(candidates) == 1:
                return self._matched(candidates[0], "organization_name")
            if len(candidates) > 1:
                return self._ambiguous("organization_name", candidates)

        return {"outcome": "not_found"}


# Loaded once per application process. Replacing the weekly file takes effect
# the next time the application starts.
UTAH_CSV_LOOKUP = UtahCsvLookup()
