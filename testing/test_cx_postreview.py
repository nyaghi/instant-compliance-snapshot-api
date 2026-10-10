"""Focused controls for the October 7 Performance Lab review."""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

import registry_snapshot_server as cc
from deployment import performance_lab


class WisconsinPossessiveComponent(unittest.TestCase):
    entered = "Cosmetic Executive Women Foundation - Cancer and Careers"
    registry = "COSMETIC EXECUTIVE WOMENS FOUNDATION LTD"

    def test_complete_component_only(self):
        self.assertTrue(cc.wi_possessive_supplied_component_match(self.entered, self.registry))
        self.assertTrue(cc.wi_possessive_supplied_component_match(
            "Northern Children's Literacy Center / Bright Futures", "NORTHERN CHILDRENS LITERACY CENTER INC"))
        for entered, registry in (
            (self.entered, "COSMETIC EXECUTIVE WOMENS FOUNDATION CHICAGO LTD"),
            (self.entered, "COSMETIC EXECUTIVE WOMENS ASSOCIATION LTD"),
            ("College of William & Mary", "COLLEGE OF WILLIAM & MARY FOUNDATION"),
            ("North Foundation - South", "NORTH FOUNDATIONS LTD"),
        ):
            with self.subTest(entered=entered, registry=registry):
                self.assertFalse(cc.wi_possessive_supplied_component_match(entered, registry))

    def test_row_acceptance_still_needs_address_corroboration(self):
        candidate = {"registry_name": self.registry, "license_number": "16588-800",
                     "location": "NEW YORK, NY", "detail_href": "", "score": 4}
        detail = "Name: COSMETIC EXECUTIVE WOMENS FOUNDATION LTD Credential Type: Charitable Organization Credential Number: 16588-800 Location: NEW YORK, NY Status: License is current (Active)"
        targets = cc.organization_match_target_variants(self.entered, "13-3563114")
        self.assertTrue(cc.wi_live_candidate_name_is_safe(
            self.registry, targets, self.entered, "13-3563114"))
        with patch.object(cc, "registry_identity_preference", return_value=1), patch.object(
                cc, "registry_address_evidence", return_value={"decision": "corroborated"}):
            matched = cc.wi_verify_candidate_identity(candidate, targets, self.entered, "13-3563114", detail)
            self.assertFalse(matched["identity_conflict"])
        with patch.object(cc, "registry_identity_preference", return_value=1), patch.object(
                cc, "registry_address_evidence", return_value={"decision": "unknown"}):
            matched = cc.wi_verify_candidate_identity(candidate, targets, self.entered, "13-3563114", detail)
            self.assertTrue(matched["identity_conflict"])

    def test_complete_registry_row_and_detail_are_selected(self):
        targets = cc.organization_match_target_variants(self.entered, "13-3563114")
        row = "| 16588-800 | Charitable Organization | [COSMETIC EXECUTIVE WOMENS FOUNDATION LTD](https://apps.dfi.wi.gov/ice/berg/Registration/CredSummaryDetails.aspx?chid=935414) | NEW YORK, NY | 08/08/2016 | 07/31/2027 |"
        detail = "Name: COSMETIC EXECUTIVE WOMENS FOUNDATION LTD Credential Type: Charitable Organization Credential Number: 16588-800 Location: NEW YORK, NY Status: License is current (Active)"
        with patch.object(cc, "wi_reader_text", return_value=detail), patch.object(
                cc, "registry_address_evidence", return_value={"decision": "corroborated"}), patch.object(
                cc, "registry_identity_preference", return_value=1):
            candidate = cc.wi_candidate_from_markdown_row(row, targets, self.entered, "13-3563114")
        self.assertIsNotNone(candidate)
        self.assertFalse(candidate["identity_conflict"])
        self.assertEqual("16588-800", candidate["license_number"])


class MississippiPlanner(unittest.TestCase):
    def test_descriptive_spaced_dash_components_precede_shortened_queries(self):
        name = "WGU Corporation - Western Governors University"
        plan = cc.ms_name_search_plan(name)
        self.assertEqual(plan[:2], [name, "Western Governors University"])
        self.assertNotIn("WGU Corporation", plan)

        independent = "Northern Children's Literacy Center - Bright Futures"
        self.assertEqual(cc.ms_name_search_plan(independent)[:3], [
            independent, "Northern Children's Literacy Center", "Bright Futures"])

        # A hyphen inside a legal name is not a separator, and generic one-word
        # fallbacks remain excluded from a multiword name.
        self.assertEqual(cc.licensed_compound_retrieval_names("Make-A-Wish Foundation"), [])
        self.assertNotIn("Avenue", cc.ms_name_search_plan("Saks Fifth Avenue Foundation"))

    def test_discard_generic_single_word_probes(self):
        for name, blocked in (("Saks Fifth Avenue Foundation", "Avenue"),
                              ("Imagine School Nonprofit", "School"),
                              ("Imagine Schools Non-Profit, Inc.", "Schools"),
                              ("International Studies Association", "Studies"),
                              ("National Church Residences Foundation", "Residences")):
            with self.subTest(name=name):
                plan = cc.ms_name_search_plan(name)
                self.assertIn(name, plan)
                self.assertNotIn(blocked, plan)
        self.assertIn("redrover", [item.casefold() for item in cc.ms_name_search_plan("United Animal Nations - RedRover")])
        self.assertIn("Avenue", cc.ms_name_search_plan("Avenue"))
        self.assertTrue(all(len(re.findall(r"[A-Za-z0-9]+", q)) > 1
                            for q in cc.ms_name_search_plan("YMCA of Greater Boston")))


class StateSelector(unittest.TestCase):
    def test_all_38_states_display_in_name_order(self):
        html = (Path(__file__).resolve().parents[1] / "web-staging" / "index.html").read_text(encoding="utf-8")
        with patch.object(performance_lab, "trial_identity", return_value={"trial": True}):
            rendered = performance_lab.final_four_asset("index.html", html)
        labels = re.findall(r'<input type="checkbox" name="states" value="([A-Z]{2})"[^>]* /> <span>([^<]+)</span>', rendered)
        self.assertEqual(38, len(labels))
        self.assertEqual(38, len(set(code for code, _ in labels)))
        self.assertEqual(sorted(labels, key=lambda pair: pair[1].casefold()), labels)
        self.assertIn('.map((box) => box.value).sort()', rendered)


if __name__ == "__main__":
    unittest.main()
