"""Replay Colorado EIN and name responses through the real collector and selector."""

from contextlib import nullcontext
import io
import json
import unittest
from unittest.mock import Mock, patch

import registry_snapshot_server as master


TRUST = "Disabled American Veterans Charitable Service Trust"
FOUNDATION = "DISABLED AMERICAN VETERANS NATIONAL SERVICE FOUNDATION"
TRUST_EIN = "52-1521276"
FOUNDATION_EIN = "52-1516071"
NO_MATCH = "No records found"


def detail(name, ein_row):
    return f"Charitable organization\nName\t{name}\nExpires on\t08/15/2027\n{ein_row}\n"


class ColoradoRecordIdentity(unittest.TestCase):
    def browser_lookup(self, responses, *, org_name=TRUST, variants=(TRUST,), expected_queries=None):
        org = master.checker.Organization(org_name, TRUST_EIN)
        page = Mock()
        page.expect_navigation.side_effect = lambda **kwargs: nullcontext()
        page.locator.return_value.inner_text.side_effect = responses
        field = Mock()
        # Keep the real form selection, parsing, identity decision, and status logic.
        with (
            patch.object(master.checker, "find_visible_input", return_value=field),
            patch.object(master.checker, "safe_wait_for_network_idle"),
            patch.object(master.checker, "fast_sleep"),
            patch.object(master, "organization_name_variants", return_value=list(variants)),
            patch.dict(master.PUBLIC_PROFILE_CACHE, {"521521276": {}}),
        ):
            result = master.search_co_with_name_fallback(page, org)
        if expected_queries is not None:
            self.assertEqual([c.args[0] for c in field.fill.call_args_list if c.args[0]], expected_queries)
        return result

    def test_saved_trust_failure_rejects_foundation_and_retains_completed_ein_no_match(self):
        result = self.browser_lookup(
            [NO_MATCH, detail(FOUNDATION, "EIN\t52-1516071\tForm\tCorporation")],
            expected_queries=["521521276", TRUST],
        )
        self.assertEqual(master.public_status(result), "Not Registered")
        self.assertEqual(result.matched_registry_name, "")
        self.assertTrue(result._cc_co_unbound_page)
        self.assertIn("excluded", result.source_note)

    def test_matching_ein_search_keeps_status_and_single_query(self):
        result = self.browser_lookup(
            [detail(TRUST, "EIN\t52-1521276\tForm\tCorporation")], expected_queries=["521521276"]
        )
        self.assertEqual(result.matched_registry_name, TRUST)
        self.assertEqual(master.public_status(result), "Current")
        self.assertFalse(getattr(result, "_cc_co_unbound_page", False))

    def test_fallback_with_exact_ein_can_recover_after_excluding_wrong_entity(self):
        result = self.browser_lookup(
            [NO_MATCH, detail(FOUNDATION, "FEIN: 52-1516071"), detail(TRUST, "EIN\n521521276")],
            variants=(TRUST, "Second valid variant"),
            expected_queries=["521521276", TRUST, "Second valid variant"],
        )
        self.assertEqual(result.matched_registry_name, TRUST)
        self.assertEqual(master.public_status(result), "Current")
        self.assertFalse(getattr(result, "_cc_co_unbound_page", False))

    def test_exact_name_with_wrong_ein_is_rejected_even_with_query_echo(self):
        result = self.browser_lookup([NO_MATCH, "Search term: 52-1521276\n" + detail(TRUST, "EIN  52-1516071")])
        self.assertEqual(master.public_status(result), "Not Registered")
        self.assertEqual(result.matched_registry_name, "")

    def test_direct_conflict_is_review_and_does_not_imply_completed_no_match(self):
        for field in ("EIN\t52-1516071", "EIN\t52-1521276\nFEIN\t52-1516071"):
            with self.subTest(field=field):
                result = self.browser_lookup([detail(TRUST, field)], expected_queries=["521521276"])
                self.assertEqual(master.public_status(result), "Unable to Confirm")
                self.assertEqual(result.matched_registry_name, "")
                self.assertTrue(result._cc_co_unbound_page)

    def test_weak_name_without_ein_stays_unconfirmed(self):
        result = self.browser_lookup([NO_MATCH, detail(FOUNDATION, "EIN\tUnavailable")])
        self.assertEqual(master.public_status(result), "Unable to Confirm")
        self.assertTrue(result._cc_co_unbound_page)

    def test_exact_name_without_ein_can_still_confirm(self):
        result = self.browser_lookup([NO_MATCH, detail(TRUST, "EIN\tUnavailable")])
        self.assertEqual(master.public_status(result), "Current")
        self.assertEqual(result.matched_registry_name, TRUST)

    def test_official_dataset_rejects_conflicting_ein_even_with_exact_name(self):
        org = master.checker.Organization(TRUST, TRUST_EIN)
        row = {"name": TRUST, "fein": FOUNDATION_EIN, "entityid": "20043001355",
               "currentstatus": "GOOD", "expirationdate": "2027-08-15"}
        with (
            patch.object(master.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps([row]).encode())),
            patch.dict(master.PUBLIC_PROFILE_CACHE, {"521521276": {}}),
        ):
            result = master.co_api_fallback_result(org)
        self.assertEqual(master.public_status(result), "Not Registered")
        self.assertEqual(result.matched_registry_name, "")
