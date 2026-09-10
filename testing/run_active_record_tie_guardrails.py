"""Duplicate-record integration controls: identity first, explicit activity second."""
import io
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc
import KS_weekly_checker as ks

class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.org = cc.checker.Organization("Example Relief", "123456789")

    def test_only_explicit_active_status_receives_preference(self):
        for status in ["Inactive", "Not Active", "Not Registered", "Closed", "Merged", "Suspended", "", "Active Relief Foundation"]:
            self.assertEqual(cc.registry_active_tiebreak(status), 0, status)
        for status in ["Active", "CURRENT", "Registered", "Good Standing"]:
            self.assertEqual(cc.registry_active_tiebreak(status), 1, status)

    def test_shared_name_strength_remains_above_activity(self):
        score = cc.checker.candidate_selection_score
        self.assertGreater(score("Example Relief", "Example Relief", "Closed"),
                           score("Example Relief Foundation", "Example Relief", "Active"))
        self.assertGreater(score("Example Relief", "Example Relief", "Active"),
                           score("Example Relief", "Example Relief", "Pending"))

    def test_missing_main_page_status_is_not_invented(self):
        row=Mock();row.evaluate.return_value={"name":"Example Relief"}
        self.assertEqual(cc.registry_candidate_fields(row)["status"], "")
        self.assertEqual(cc.registry_exact_active_tiebreak("Example Relief Academy", ["Example Relief"], "Active"), 0)

    def test_maryland_filters_ein_before_tie_breaking(self):
        def row(identifier, name, status, ein="123456789"):
            return {"id":identifier, "f_aedd5545-808f-4725-9b1d-5fa61e994a75":name,
                    "view_data":{"content_element_data":{"status":f"<p><strong>Registration Status:</strong> <var>{status}</var></p>",
                    "ein":f"<p><strong>Charity EIN:</strong> <var>{ein}</var></p>"}}}
        closed=row("1","Example Relief","Closed");active=row("2","Example Relief","Active")
        for entries in ([closed,active],[active,closed]):
            entries=[row("wrong","Example Relief","Active","987654321"), *entries]
            body=cc.md_prefer_active_entry_body(json.dumps({"success":True,"entries":entries}), self.org)
            self.assertEqual(json.loads(body)["entries"][0]["id"],"2")
        body=cc.md_prefer_active_entry_body(json.dumps({"entries":[closed,row("weak","Example Relief Academy","Active")]}),self.org)
        self.assertEqual(json.loads(body)["entries"][0]["id"],"1")

    def test_california_same_identity_active_before_newer_closed(self):
        closed={"id":"1","entityName":"Example Relief","fein":"123456789","entityStatus":"Closed"}
        active={**closed,"id":"2","entityStatus":"Active"}
        def classify(entity, registrations):
            return ("Current" if entity["id"]=="2" else "Closed", entity["entityStatus"], entity["id"], date(2027 if entity["id"]=="2" else 2028,1,1))
        for entities in ([closed,active],[active,closed]):
            with patch.object(cc.checker,"ca_evoke_entity_search_by_ein",return_value=entities), \
                 patch.object(cc.checker,"ca_evoke_registrations_for_entity",return_value=[]), \
                 patch.object(cc.checker,"ca_evoke_status_from_record",side_effect=classify):
                result=cc.checker.search_ca(Mock(),self.org)
            self.assertEqual(result.matched_registry_identifier,"2")

    def test_colorado_same_identity_active_before_newer_closed(self):
        closed={"entityid":"1","name":"Example Relief","currentstatus":"Closed","registrationapproveddate":"2026-01-01","expirationdate":"2028-01-01"}
        active={**closed,"entityid":"2","currentstatus":"Active","registrationapproveddate":"2025-01-01"}
        for rows in ([closed,active],[active,closed]):
            with patch.object(cc.urllib.request,"urlopen",return_value=io.BytesIO(json.dumps(rows).encode())), \
                 patch.object(cc,"result_registry_name_is_safe",return_value=True):
                result=cc.co_api_fallback_result(self.org)
            self.assertEqual(result.matched_registry_identifier,"2")

    def test_south_carolina_chooses_active_on_main_page_before_one_detail_visit(self):
        session=Mock();session.get.return_value.text="<form></form>"
        def post(url,data,**kwargs):
            identifier=data.get("ctl00$MainContent$Hidden_CharityID")
            body=(f"Public Id P{identifier} Status {'Active' if identifier=='2' else 'Closed'} Due Date 12/31/2027" if identifier else
                  '<table><tr><th>Name</th><th>Status</th></tr><tr><td><a href="javascript:CharityInfo(1)">Example Relief</a></td><td>Closed</td></tr><tr><td><a href="javascript:CharityInfo(2)">Example Relief</a></td><td>Registered</td></tr></table>')
            # SC's official active vocabulary is Registered.
            return SimpleNamespace(text=body.replace("Status Active","Status Registered"),raise_for_status=lambda:None)
        session.post.side_effect=post
        with patch.object(cc,"curl_requests",Mock(Session=Mock(return_value=session))), \
             patch.object(cc,"build_search_queries",return_value=["Example Relief"]):
            result=cc.sc_official_detail_lookup(self.org)
        self.assertEqual(result.matched_registry_identifier,"P2")
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(result.status,"Current")

    def test_michigan_main_row_active_wins_only_exact_name_tie(self):
        rows=[]
        for name,status,identifier in [("Example Relief","Closed","1"),("Example Relief","Active","2"),("Example Relief Academy","Active","3")]:
            link=Mock();link.get_attribute.return_value="javascript:btnOrgName"+identifier;link.inner_text.return_value=name
            link.locator.return_value.evaluate.return_value={"name":name,"status":status}
            rows.append(link)
        frame=Mock();frame.locator.return_value.count.return_value=len(rows)
        module=SimpleNamespace(normalize_name=cc.normalized_match_name)
        for ordered in (rows,list(reversed(rows))):
            frame.locator.return_value.nth.side_effect=ordered.__getitem__
            chosen=cc.mi_choose_result_link(frame,"Example Relief",module)
            self.assertEqual(chosen[3],"javascript:btnOrgName2")

    def test_connecticut_main_row_name_strength_precedes_status(self):
        def row(name,status):
            return f'<tr><td><b class="headline6">{name}</b><b>Credential</b><p>CHR.001</p><b>Status</b><p>{status}</p><b>Credential Description</b><p>PUBLIC CHARITY</p></td></tr>'
        with patch.object(cc,"ct_direct_detail_text",return_value=""):
            closed,_=cc.ct_direct_result_from_row(self.org,row("Example Relief","Closed"),["Example Relief"],"fixture")
            active,_=cc.ct_direct_result_from_row(self.org,row("Example Relief","Active"),["Example Relief"],"fixture")
        self.assertGreater(active.selection_rank,closed.selection_rank)
        self.assertEqual(closed.status,"Closed / Withdrawn / Canceled")

    def test_mississippi_current_beats_not_current_for_exact_name(self):
        closed=Mock();closed.inner_text.return_value="Example Relief Not Current 12/31/2028"
        active=Mock();active.inner_text.return_value="Example Relief Current 12/31/2027"
        table=Mock();table.locator.return_value.count.return_value=2
        for rows in ([closed,active],[active,closed]):
            table.locator.return_value.nth.side_effect=rows.__getitem__
            with patch.object(cc,"ms_result_row_cells",return_value=["Example Relief","status"]), \
                 patch.object(cc,"ms_registry_name_from_row",return_value="Example Relief"), \
                 patch.object(cc,"ms_status_from_row_cells",side_effect=lambda row:"Current" if row is active else "Not Current"):
                self.assertIs(cc.ms_choose_safe_row_from_table(table,"Example Relief","123456789"),active)

    def test_kansas_not_registered_is_not_a_registered_substring(self):
        closed=SimpleNamespace(ein="123456789",status="Not Registered",expire_date=date(2028,1,1))
        active=SimpleNamespace(ein="123456789",status="Registered",expire_date=date(2027,1,1))
        self.assertIs(ks.find_ein_match([closed,active],"123456789"),active)
        self.assertIs(ks.find_ein_match([active,closed],"123456789"),active)

if __name__ == "__main__": unittest.main()
