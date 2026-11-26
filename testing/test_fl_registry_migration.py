from concurrent.futures import Future
from datetime import date, timedelta
from html import escape
import json
import os
from pathlib import Path
import time
import unittest
from unittest.mock import MagicMock, patch

from deployment.fl_registry_migration import MigrationCheck, URL, capture, parse, query_url
from deployment.state_snapshots import CaptureRun, public_url
import registry_snapshot_server as cc


def document(query, cards=(), *, result_count=None):
    query = escape(query, quote=True)
    page = ('<!DOCTYPE html><html><body><div class="lr-scope">Search Licenses'
            f'<form><input name="search_name" value="{query}"></form>')
    if cards:
        number = len(cards) if result_count is None else result_count
        page += f'<span>{number} record(s)</span>'
        for ident, name, status, expiration, location, ein in cards:
            ident, name, status, expiration, location, ein = map(escape, (ident, name, status, expiration, location, ein))
            page += (f'<div class="license-item" data-print-name="{name}" data-print-reg="{ident}" '
                     f'data-print-status="{status}" data-print-expiration="{expiration}" data-print-location="{location}">'
                     f'<h3>{name}</h3><dl><dt>Registration Number</dt><dd>{ident}<span>{status}</span></dd>'
                     f'<dt>Expiration Date</dt><dd>{expiration or "N/A"}</dd><dt>Location</dt><dd>{location}</dd>'
                     + (f'<dt>FEIN</dt><dd>{ein}</dd>' if ein else '') + '</dl></div>')
        page += f'<div>Showing 1 to {len(cards)} of {number} results</div>'
    else:
        page += '<div class="alert alert-warning">No licenses found matching your search.</div>'
    return page + '</div></body></html><!-- Generated at 11/26/2026 5:49:18 PM --><!-- Page OK -->'


class FloridaMigration(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization("A Regional Charity", "12-3456789")
        self.deadline = time.monotonic() + 6
        self.expiration = (date.today() + timedelta(days=300)).strftime("%m/%d/%Y")

    def row(self, **args):
        value = dict(identifier="CH12345", name=self.org.organization_name, status="Registered",
                     expiration=self.expiration, location="N/A", ein=self.org.ein)
        value.update(args)
        return tuple(value.values())

    def old(self, status="Not Registered", identifier=""):
        result = cc.checker.StateResult(self.org.organization_name, self.org.ein, "FL", status,
            cc.FL_CHECK_A_CHARITY_URL, source_note="Legacy search returned.", success=status != "Site Not Reachable")
        result.matched_registry_identifier = identifier
        return result

    def merge(self, old, pages, *, legacy_complete=True):
        with CaptureRun(self.org.organization_name, self.org.ein, "FL") as run:
            name = self.org.organization_name
            run.fl_query_progress = {"completed": {name: old} if legacy_complete else {}}
            task = MigrationCheck(cc, run)
            task.deadline = self.deadline
            task.names = (name,)
            task.prior_pages = {}
            task.future = Future()
            task.future.set_result({q: (parse(doc, q), doc) for q, doc in pages.items()})
            result = task.finish(old, self.org)
            return result, run

    def test_bound_empty_and_partial_response(self):
        name = self.org.organization_name
        self.assertEqual(parse(document(name), name), ())
        for bad, query in ((document(name), "Different filer"),
                           (document(name).replace("</html>", ""), name),
                           (document(name, [self.row()], result_count=2), name),
                           (document(name, [self.row()]).replace("<span>Registered", "<span>Expired"), name),
                           (document(name).replace("Search Licenses", "Verify you are human"), name)):
            with self.assertRaises(ValueError):
                parse(bad, query)

    def test_two_completed_negatives_are_required(self):
        name = self.org.organization_name
        result, run = self.merge(self.old(), {name: document(name)})
        self.assertEqual(result.status, "Not Registered")
        self.assertEqual(run.search_history_receipts[0]["returned_rows"], 0)
        self.assertIn(URL, run.search_history_receipts[0]["query"]["url"])
        self.assertEqual(self.merge(self.old(), {})[0].status, "Unable to Confirm")
        self.assertEqual(self.merge(self.old(), {name: document(name)}, legacy_complete=False)[0].status, "Unable to Confirm")
        self.assertEqual(self.merge(self.old("Site Not Reachable"), {name: document(name)})[0].status,
                         "Site Not Reachable")

    def test_verified_modern_statuses_recover_old_failure(self):
        name = self.org.organization_name
        for label, expiration, expected in (
            ("Registered", self.expiration, "Current"),
            ("Suspended", "", "Suspended"),
            ("Revoked", "", "Revoked"),
            ("Law NA - Educational", "", "Exempt"),
            ("Expired", "10/10/2023", "Delinquent"),
        ):
            with self.subTest(label=label):
                row = self.row(status=label, expiration=expiration)
                result, run = self.merge(self.old("Site Not Reachable"), {name: document(name, [row])})
                self.assertEqual(result.status, expected)
                self.assertEqual(result.matched_registry_identifier, "CH12345")
                self.assertEqual(run.fl_modern_selected[-1], row)

    def test_wrong_ein_excluded_and_opaque_or_ambiguous_rows_remain_inconclusive(self):
        name = self.org.organization_name
        wrong_ein = self.row(ein="87-6543210")
        self.assertEqual(self.merge(self.old(), {name: document(name, [wrong_ein])})[0].status, "Not Registered")
        for cards in ([self.row(name="CH12345", ein="")], [self.row(ein="")],
                      [self.row(), self.row(identifier="CH44455")]):
            result, _ = self.merge(self.old(), {name: document(name, cards)})
            self.assertEqual(result.status, "Unable to Confirm")
            self.assertIn("CH12345", result.source_note)

    def test_legacy_wrong_ein_guard_also_applies_to_new_source_card(self):
        name = self.org.organization_name
        result = self.old()
        result.rejected_candidates = [{"identifier": "CH12345", "ein": "87-6543210"}]
        recovered, _ = self.merge(result, {name: document(name, [self.row(ein="")])})
        self.assertEqual(recovered.status, "Not Registered")

    def test_existing_verified_positive_is_returned_without_waiting_for_new_portal(self):
        result = self.old("Exempt", "CH54321")
        check = MigrationCheck(cc, None)
        check.future = MagicMock()
        self.assertIs(check.finish(result, self.org), result)
        check.future.result.assert_not_called()

    def test_only_new_charity_path_is_authorized_for_florida_archives(self):
        self.assertIn(URL, public_url(query_url(self.org.organization_name), "FL"))
        for url, state in ((URL, "GA"), (URL.replace("/Check-A-Charity/", "/Business-Search/"), "FL"),
                           (URL + "#different", "FL")):
            with self.assertRaises(ValueError):
                public_url(url, state)

    def test_aurora_entry_only_enables_the_companion_for_matching_staging_scope(self):
        name = self.org.organization_name
        for identity, mode, expected in (({"permanent_staging": True}, "standard", True),
                                         ({}, "standard", False),
                                         ({"permanent_staging": True}, "sales", False)):
            with self.subTest(mode=mode, enabled=expected), CaptureRun(name, self.org.ein, "FL") as run:
                run.semantic_history_scope = True
                token = cc.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:
                    with patch.object(cc, "trial_identity", return_value=identity), patch.object(
                            cc, "search_fl_with_transport", return_value=self.old("Exempt", "CH54321")) as legacy:
                        self.assertEqual(cc.search_fl(MagicMock(), self.org).status, "Exempt")
                        self.assertEqual("migration" in legacy.call_args.kwargs, expected)
                finally:
                    cc.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_original_card_snapshot_is_bound_before_and_after_capture(self):
        name = self.org.organization_name
        result, run = self.merge(self.old(), {name: document(name, [self.row()])})
        page = MagicMock()
        page.url = result.source_url
        page.content.return_value = document(name, [self.row()])
        card = page.locator.return_value
        card.count.return_value = 1
        card.inner_text.return_value = f"{name}\nCH12345\nRegistered\n{self.expiration}"
        card.screenshot.return_value = b"test image"
        def render(url, **options):
            handler = page.route.call_args.args[1]
            route = MagicMock()
            route.request.url = url
            route.request.method = "GET"
            route.request.resource_type = "document"
            handler(route)
            self.assertEqual(route.fulfill.call_args.kwargs["body"], page.content.return_value)
            response = MagicMock()
            response.status = 200
            return response
        page.goto.side_effect = render
        data = dict(source_url=result.source_url, matched_registry_identifier="CH12345",
                    matched_registry_name=name)
        capture(run, data, page, self.deadline)
        self.assertEqual(len(run.documents), 1)
        self.assertEqual(run.documents[0][:3], (result.source_url, b"test image", "image"))
        card.inner_text.side_effect = ["First record", "Different record"]
        capture(run, data, page, self.deadline)
        self.assertEqual(len(run.documents), 1)

    def test_saved_public_pages(self):
        path = os.environ.get("CC_FL_MIGRATION_FIXTURES")
        if not path:
            self.skipTest("Provide the saved official FDACS pages.")
        root = Path(path)
        self.assertEqual(parse((root / "new-uso.html").read_text(encoding="utf-8"), "United service"), ())
        cards = parse((root / "modern-ywca-license.html").read_text(encoding="utf-8"), "CH3385")
        self.assertEqual(cards[0], ("CH3385", "CH3385", "Registered", "10/22/2027", "N/A", ""))
        self.assertEqual(parse((root / "new-pittsburgh-id.html").read_text(encoding="utf-8"), "CH52211"), ())

    def test_double_escaped_query_still_requires_exact_match(self):
        name = "Children's Hunger Fund"
        source = document(name).replace("&#x27;", "&amp;#39;")
        self.assertEqual(parse(source, name), ())
        with self.assertRaisesRegex(ValueError, "not bound"):
            parse(source, "Childrens Hunger Fund")
        with self.assertRaisesRegex(ValueError, "not bound"):
            parse(source.replace("&amp;#39;", "&amp;amp;#39;"), name)

    def test_recorded_organization_matrix(self):
        path = os.environ.get("CC_FL_MIGRATION_ROSTER")
        if not path:
            self.skipTest("Provide at least 100 distinct archived audit organizations.")
        roster = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertGreaterEqual(len({r["ein"] for r in roster}), 100)
        for org in roster:
            self.org = cc.checker.Organization(org["name"], org["ein"])
            name = self.org.organization_name
            complete_empty = {name: document(name)}
            scenarios = [
                (self.old(), complete_empty, "Not Registered"),
                (self.old(), {}, "Unable to Confirm"),
                (self.old("Site Not Reachable"), complete_empty, "Site Not Reachable"),
                (self.old("Exempt", "CH54321"), {}, "Exempt"),
                (self.old(), {name: document(name, [self.row(ein="00-0000000")])}, "Not Registered"),
                (self.old("Site Not Reachable"), {name: document(name, [self.row()])}, "Current"),
                (self.old(), {name: document(name, [self.row(name="CH12345", ein="")])}, "Unable to Confirm"),
            ]
            for legacy, pages, expected in scenarios:
                with self.subTest(ein=org["ein"], expected=expected):
                    self.assertEqual(self.merge(legacy, pages)[0].status, expected)
