"""Published Kansas workbook header compatibility; no registry requests."""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import KS_weekly_checker as ks
import registry_snapshot_server as cc


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


class KansasCompoundNameSearch(unittest.TestCase):
    def lookup(self, name):
        module = cc.load_ks_weekly_checker()
        records = [
            module.KSRecord("21-023650", "Sexually Abused Children's Relief Endeavor",
                            "Expired", date(2026, 6, 30), "Overland Park", "KS", "66210"),
            module.KSRecord("21-000001", "SACRED PEOPLE FOUNDATION, INC.",
                            "Registered", date(2027, 6, 30), "Trumbull", "CT", "66110"),
            module.KSRecord("21-000002", "Community Food Relief Foundation",
                            "Registered", date(2027, 6, 30), "Topeka", "KS", "66603"),
        ]
        with (patch.object(cc, "weekly_asset", return_value=True),
              patch.object(module, "load_live_records", return_value=(records, "https://example.test/ks.xlsx", "https://example.test/ks")),
              patch.object(module, "make_snapshot_image", return_value="")):
            org = cc.checker.Organization(organization_name=name, ein="27-0567085")
            return cc.search_snapshot_or_embedded_state(org, "KS")

    def test_descriptive_pre_dash_name_finds_record(self):
        result = self.lookup("Sexually Abused Children's Relief Endeavor \u2014 SACRED")
        self.assertEqual(result.status, "Delinquent/Non-compliant")
        self.assertEqual(result.matched_registry_identifier, "21-023650")

    def test_similar_legal_name_and_one_word_brand_do_not_confirm_identity(self):
        result = self.lookup("Sexually Abused Children's Relief Foundation \u2014 SACRED")
        self.assertEqual(result.status, "Not registered")
        self.assertFalse(result.matched_registry_identifier)

    def test_independent_descriptive_pre_dash_name_uses_same_rule(self):
        result = self.lookup("Community Food Relief Foundation \u2014 CFRF")
        self.assertEqual(result.matched_registry_identifier, "21-000002")


if __name__ == "__main__":
    unittest.main(verbosity=2)
