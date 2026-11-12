"""Regression coverage for Nevada's overlapping reviewed and generated queries."""
from unittest import TestCase
from unittest.mock import patch

import registry_snapshot_server as cc


CASEY = "Annie E. Casey Foundation"
CASEY_EIN = "521951681"
CASEY_ALIASES = [
    "ANNIE E CASEY FOUNDATION INC",
    "CASEY, ANNIE E. FOUNDATION, INC",
    "THE ANNIE E. CASEY FOUNDATION, INC.",
]


class NevadaSearchCoverage(TestCase):
    def setUp(self):
        self.calls = []
        context = cc.REVIEWED_NAME_CONTEXT.set({CASEY_EIN: CASEY_ALIASES})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset, context)
        staging = patch.object(cc, "trial_identity", return_value={"permanent_staging": True})
        staging.start()
        self.addCleanup(staging.stop)

    def lookup(self, *, exact=(), incomplete=()):
        def source(query):
            name = query["name"]
            self.calls.append(name)
            narrowed = name in exact
            return dict(state="NV", query=query, complete=name not in incomplete,
                        verification_pending=False, rows=[], total=0,
                        search_mode="EXACT_MATCH" if narrowed else "STARTS_WITH",
                        broad_total=21 if narrowed else None)

        return cc.final_four_browser_lookup(cc.checker.Organization(CASEY, CASEY_EIN), "NV", source)

    def test_casey_reuses_complete_prefixes_and_keeps_distinct_spellings(self):
        result = self.lookup()
        self.assertEqual(result.status, "Not Registered")
        self.assertEqual(self.calls[0], CASEY)
        self.assertEqual(len(self.calls), 9)
        for name in CASEY_ALIASES:
            self.assertNotIn(name, self.calls)
        self.assertIn("CASEY ANNIE E", self.calls)
        self.assertIn("Annie-E. Casey Foundation", self.calls)
        self.assertIn("ANNIE-E CASEY FOUNDATION", self.calls)
        covered = {item["reviewed_name_coverage"]["name"] for item in result.source_attempts}
        self.assertEqual(covered, set(CASEY_ALIASES))

    def test_exact_match_cannot_cover_longer_reviewed_name(self):
        result = self.lookup(exact={"Annie E Casey"})
        self.assertEqual(result.status, "Not Registered")
        self.assertLess(self.calls.index("Annie E Casey"), self.calls.index(CASEY_ALIASES[0]))

    def test_incomplete_prefix_cannot_support_a_negative(self):
        with self.assertRaisesRegex(ValueError, "did not return a complete result set"):
            self.lookup(incomplete={"Annie E Casey"})
