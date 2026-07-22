from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from utah_csv_lookup import REQUIRED_COLUMNS, UtahCsvLookup


ALL_COLUMNS = [*REQUIRED_COLUMNS, "SOURCE", "NOTES"]


class UtahCsvLookupTests(unittest.TestCase):
    def write_csv(self, rows: list[dict[str, str]], columns: list[str] | None = None) -> Path:
        path = Path(self.temp_dir.name) / "utah.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns or ALL_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_exact_normalized_ein_match_preserves_csv_values(self) -> None:
        path = self.write_csv([{
            "DATE CHECKED": "7/19/2026",
            "ORG NAME": "AAA CLUB ALLIANCE INC.",
            "EIN": "12-3456789",
            "STATUS": "Current - copied literally",
            "EXPIRATION DATE": "1/31/2027",
            "SOURCE": "weekly list",
            "NOTES": "",
        }])
        result = UtahCsvLookup(path).lookup("Wrong Name", "12 345-6789")
        self.assertEqual(result["outcome"], "matched")
        self.assertEqual(result["matched_by"], "ein")
        self.assertEqual(result["organization_name"], "AAA CLUB ALLIANCE INC.")
        self.assertEqual(result["ein"], "12-3456789")
        self.assertEqual(result["status"], "Current - copied literally")
        self.assertEqual(result["expiration_date"], "1/31/2027")
        self.assertEqual(result["last_date_checked"], "7/19/2026")

    def test_exact_normalized_organization_name_match(self) -> None:
        path = self.write_csv([{
            "DATE CHECKED": "",
            "ORG NAME": "Alpha & Beta, Inc.",
            "EIN": "",
            "STATUS": "",
            "EXPIRATION DATE": "",
            "SOURCE": "",
            "NOTES": "",
        }])
        result = UtahCsvLookup(path).lookup("  ALPHA   BETA INC  ", "")
        self.assertEqual(result["outcome"], "matched")
        self.assertEqual(result["matched_by"], "organization_name")
        self.assertEqual(result["organization_name"], "Alpha & Beta, Inc.")
        self.assertEqual(result["status"], "")
        self.assertEqual(result["expiration_date"], "")
        self.assertEqual(result["last_date_checked"], "")

    def test_no_match(self) -> None:
        path = self.write_csv([])
        self.assertEqual(UtahCsvLookup(path).lookup("Missing Org", "12-3456789")["outcome"], "not_found")

    def test_duplicate_normalized_name_is_ambiguous(self) -> None:
        rows = [
            {"DATE CHECKED": "1/1/2026", "ORG NAME": "Same Org, Inc.", "EIN": "11-1111111", "STATUS": "A", "EXPIRATION DATE": "", "SOURCE": "", "NOTES": ""},
            {"DATE CHECKED": "1/2/2026", "ORG NAME": "SAME ORG INC", "EIN": "22-2222222", "STATUS": "B", "EXPIRATION DATE": "", "SOURCE": "", "NOTES": ""},
        ]
        result = UtahCsvLookup(self.write_csv(rows)).lookup("same org inc", "")
        self.assertEqual(result["outcome"], "ambiguous")
        self.assertEqual(result["candidate_count"], 2)

    def test_missing_csv_file(self) -> None:
        result = UtahCsvLookup(Path(self.temp_dir.name) / "missing.csv").lookup("Any Org", "")
        self.assertEqual(result["outcome"], "error")
        self.assertEqual(result["error_code"], "UTAH_CSV_FILE_NOT_FOUND")
        self.assertIn("not found", result["error"])

    def test_missing_required_column_lists_column(self) -> None:
        columns = [column for column in ALL_COLUMNS if column != "STATUS"]
        path = self.write_csv([], columns=columns)
        result = UtahCsvLookup(path).lookup("Any Org", "")
        self.assertEqual(result["outcome"], "error")
        self.assertEqual(result["error_code"], "UTAH_CSV_MISSING_COLUMNS")
        self.assertIn("STATUS", result["error"])


if __name__ == "__main__":
    unittest.main()
