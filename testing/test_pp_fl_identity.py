import unittest
from unittest.mock import patch

import registry_snapshot_server as cc
from testing import run_fl_alias_address_guardrails as fl_fixtures


class FloridaEinControls(unittest.TestCase):
    def setUp(self):
        self.h = fl_fixtures.FloridaAliasControls()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)

    def lookup(self, row, followup=None, proof=None):
        rows = [[row], [followup or self.h.row("Unrelated Other Charity")]]
        with patch.object(cc, "public_nonprofit_ein_at_location", return_value=proof or {}):
            return self.h.run_lookup(rows, [{"decision": "conflict"}])[0]

    def test_alias_different_ein_is_excluded_after_completed_search(self):
        result = self.lookup(self.h.row(), proof={"ein": "987654321"})
        self.assertEqual(result.status, cc.checker.STATUS_NOT_REGISTERED)
        self.assertEqual(result.rejected_candidates[0]["identifier"], "CH900")

    def test_alias_without_ein_proof_keeps_review(self):
        result = self.lookup(self.h.row())
        self.assertEqual(result.reason_code, "FL_ALIAS_IDENTITY_UNCONFIRMED")

    def test_same_name_visible_different_ein_is_excluded(self):
        row = self.h.row("Example Relief Inc")
        row["text"] += " FEIN: 98-7654321"
        result = self.lookup(row)
        self.assertEqual(result.status, cc.checker.STATUS_NOT_REGISTERED)

    def test_other_credential_same_name_does_not_inherit_the_rejection(self):
        primary = self.h.row("Example Relief Inc")
        primary["text"] += " FEIN: 98-7654321"
        result = self.lookup(primary, self.h.row("Example Relief Inc", credential="CH203"))
        self.assertEqual(result.matched_registry_identifier, "CH203")
