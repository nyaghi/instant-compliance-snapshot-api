"""Published Kansas workbook header compatibility; no registry requests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import KS_weekly_checker as ks


class KansasWorkbookHeaders(unittest.TestCase):
    def parse(self, headers):
        rows = [headers, ["26-001234", "Example Education Foundation", "Registered", 46568,
                          "1 Main Street", "", "Topeka", "KS", "66603"]]
        with patch.object(ks, "iter_sheet_rows", return_value=iter(rows)):
            return ks.records_from_workbook_bytes(b"fixture")

    def test_old_and_new_headers_preserve_same_record(self):
        old = self.parse(["ContactNo", "Name", "Status", "Expiredate", "Add1", "Add2", "City", "State1", "Zip"])
        new = self.parse(["Registration #", "Organization Name", "Status", "Expiredate", "Add1", "Add2", "City", "State1", "Zip"])
        self.assertEqual(old, new)
        self.assertEqual(new[0].contact_number, "26-001234")
        self.assertEqual(new[0].name, "Example Education Foundation")
        self.assertEqual(new[0].status, "Registered")
        self.assertIsNotNone(new[0].expire_date)

    def test_unknown_name_header_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing expected"):
            self.parse(["Registration #", "Unrelated", "Status"])

    def test_missing_status_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing expected"):
            self.parse(["Registration #", "Organization Name", "Unrelated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
