from types import SimpleNamespace
from unittest import TestCase

import registry_snapshot_server as master
from deployment.gates4243_repairs import ky_reviewed_alias, nh_parenthetical_alias, ks_country_alias
from deployment.source_visual_adapters import ca_exempt_entity_core, remember_ca_exempt_entity
from KS_weekly_checker import load_live_records, find_best_match


class Gate4243Tests(TestCase):
    def test_kentucky_exact_reviewed_alias_and_neighbors(self):
        rows = master.load_ky_snapshot_records()
        selected = [row for row in rows if ky_reviewed_alias("95-1985500", "AARP", *row[:2])]
        self.assertEqual([(r[0], r[1], r[2]) for r in selected], [("3717", "AARP Advocacy", "2024")])
        for ein, name, ident, source in [
            ("95-1985501", "AARP", "3717", "AARP Advocacy"),
            ("95-1985500", "AARP Foundation", "3717", "AARP Advocacy"),
            ("95-1985500", "AARP", "3718", "AARP Foundation"),
            ("95-1985500", "AARP", "3717", "AARP Advocacy Foundation"),
            ("95-1985500", "AARP", "3718", "AARP Advocacy"),
        ]:
            self.assertFalse(ky_reviewed_alias(ein, name, ident, source))

    def test_nh_parenthetical_identity_and_scope(self):
        aarp = "American Association of Retired Persons"
        names = ["AARP", aarp]
        self.assertTrue(nh_parenthetical_alias("AARP", names, f"AARP ({aarp})"))
        self.assertTrue(nh_parenthetical_alias(aarp, names, f"AARP ({aarp})"))
        for source in ["AARP Foundation", f"AARP ({aarp}) Foundation",
                       f"AARP Foundation ({aarp})", f"AARP ({aarp} of New England)",
                       "AARP (AARP)", "AARP (Advocacy)", f"AAU ({aarp})"]:
            self.assertFalse(nh_parenthetical_alias("AARP", names, source))
        self.assertFalse(nh_parenthetical_alias("AARP", ["AARP"], f"AARP ({aarp})"))
        self.assertFalse(nh_parenthetical_alias("AARP Foundation", names, f"AARP ({aarp})"))

    def test_kansas_recovers_only_bound_country_abbreviation(self):
        rows, *_ = load_live_records()
        original = "Amateur Athletic Union of the United States, Inc."
        self.assertIsNone(find_best_match(rows, original))
        matches = [row for row in rows if ks_country_alias(original, "35-6057862", row)]
        self.assertEqual([(r.contact_number, r.status) for r in matches], [("21-026889", "Expired")])
        for original_override, ein in [("Amateur Athletic Union Foundation of the United States", "35-6057862"),
                                       ("Amateur Athletic Union of the United States", "35-6057863"),
                                       ("Amateur Athletic Union of the United States New England", "35-6057862")]:
            self.assertFalse(ks_country_alias(original_override, ein, matches[0]))
        self.assertFalse(ks_country_alias(original, "35-6057862", SimpleNamespace(
            **{**vars(matches[0]), "ein": "350000000"})))

    def test_california_exact_990_pf_handoff_and_visible_binding(self):
        name = "ANNIE E CASEY FOUNDATION INC"
        result = SimpleNamespace(success=True, status="Exempt", matched_registry_identifier="6032089",
                                 matched_registry_name=name, _cc_registration_records=[],
                                 _cc_selected_entity={"id": "6032089", "entityName": name,
                                                      "fein": "52-1951681", "entityStatus": "Exempt 990-PF"})
        run = SimpleNamespace(state="CA", ein="521951681", source_detail_hints={})
        def remember(identifier, matched, url):
            run.source_detail_hints[identifier] = {"name": matched, "url": url}
        run.remember_detail = remember
        remember_ca_exempt_entity(run, result)
        self.assertEqual(run.source_detail_hints["6032089"]["exempt_entity_status"], "Exempt 990-PF")
        text = f"Entity Details: {name}\nExempt 990-PF\nFEIN: 52-1951681\nEntity Type Charity\nEntity Name {name}\nDBA\nEntity Status Exempt 990-PF\nOut of State? Yes"
        self.assertTrue(ca_exempt_entity_core(text, name, run.ein, "Exempt 990-PF"))
        for content in [text.replace("52-1951681", "52-1951682"), text.replace("990-PF", "990-X"),
                        text.replace("Exempt 990-PF", "Exempt"), text + "\nAccess denied"]:
            self.assertIsNone(ca_exempt_entity_core(content, name, run.ein, "Exempt 990-PF"))
        self.assertIsNone(ca_exempt_entity_core(text, name, run.ein))

    def test_ohio_partially_exempt_detail_keeps_name_and_status(self):
        org = "A. T. Still University of Health Sciences"
        body = (f"Organization Name {org} Description of Organization’s Purpose Teaching. "
                "Employer Identification Number (EIN) 43-0356250 Organization Phone 123 "
                "Registration Status Registered Exemption Status Trust (Exempt 109) "
                "Annual Reports Filed Most Recent Report Filing Year 2025 Fiscal Year End June")
        result = master.checker.StateResult(org, "43-0356250", "OH", "Unknown", "")
        result = master.oh_result_from_detail_text(result, body,
            "https://charitableregistration.ohioago.gov/Charities/PartiallyExemptOrganization?Id=1481174&ExemptionStatus=109", "1481174")
        self.assertEqual(result.matched_registry_name, org)
        self.assertEqual(result.status, "Exempt")

    def test_nc_rate_limit_receipt_remains_incomplete(self):
        from deployment.search_history import failed_receipt, manifest, needs_search_history
        from deployment.state_snapshots import completed_negative_result
        failure = 'NY_CONNECTOR_NC_RATE_LIMITED'
        record = {'state': 'NC', 'purpose': 'registration', 'ein': '381359264',
                  'organization_name': 'W. K. Kellogg Foundation', 'issued': 100,
                  'pending': {'query_id': 'signed', 'query': {
                      'state': 'NC', 'operation': 'search', 'name': 'K Kellogg'}}}
        failed_receipt(record, {'query_id': 'other', 'reason': failure}, 103)
        self.assertNotIn('search_failed_receipts', record)
        failed_receipt(record, {'query_id': 'signed', 'reason': failure}, 104)
        result = {'state': 'NC', 'ein': '381359264', 'status': 'Needs Review',
                  'success': False, 'status_reason': failure}
        self.assertTrue(needs_search_history(result))
        self.assertFalse(completed_negative_result(result))
        receipt = manifest(record, result, {}, 106)
        self.assertTrue(receipt['incomplete_search'])
        self.assertEqual(receipt['queries'][0]['reason'], failure)
        self.assertIsNone(receipt['queries'][0]['completed_at'])
        self.assertFalse(needs_search_history({**result, 'status_reason': 'VERIFICATION_REQUIRED'}))

    def test_kentucky_reviewed_alias_survives_full_lookup(self):
        org = master.checker.Organization("AARP", "95-1985500")
        result = master.search_snapshot_or_embedded_state(org, "KY")
        self.assertEqual(result.matched_registry_identifier, "3717")
        self.assertEqual(result.matched_registry_name, "AARP Advocacy")
        wrong = master.checker.Organization("AARP Foundation", "95-1985500")
        self.assertNotEqual(master.search_snapshot_or_embedded_state(wrong, "KY").matched_registry_identifier, "3717")

    def test_massachusetts_activity_evidence_stays_bound_and_unresolved(self):
        import hashlib
        from deployment.ma_view_more_evidence import preserves_activity_identity, select
        from deployment.state_snapshots import CURRENT
        name = "Annie E Casey Foundation Inc"
        ein = "521951681"
        account = "027225"
        url = "https://masscharities.my.site.com/FilingSearch/s/"
        text = f"{name}\nAG Account Number: {account}\nEIN: 52-1951681"
        document = (url, b"retained-image", "image", text, 0, "")
        record = {"name": name, "ein": ein, "ago_account": account, "registry_status": "Not Doing Business in Mass"}
        run = SimpleNamespace(state="MA", ein=ein, documents=[document], ma_view_more_bindings={
            hashlib.sha256(document[1]).hexdigest(): {"record": record, "url": url, "role": "main"}})
        row = dict(state="MA", ein=ein, matched_registry_name=name, matched_registry_identifier=account,
                   success=True, status="Unable to Confirm", status_reason="MA_FORM_PC_DETAIL_UNCONFIRMED",
                   ma_filing_evidence={"registry_status": "Not Doing Business in Mass", "ago_account": account})
        token = CURRENT.set(run)
        try:
            self.assertTrue(preserves_activity_identity(SimpleNamespace(**row)))
            self.assertEqual(select(run, [document], row), [document])
            for text_change in (text.replace(account, "027226"), text.replace("52-1951681", "52-1951682"),
                                text.replace(name, "Other Foundation")):
                run.documents = [(*document[:3], text_change, *document[4:])]
                self.assertFalse(preserves_activity_identity(SimpleNamespace(**row)))
                self.assertEqual(select(run, run.documents, row), [])
            self.assertEqual(select(run, [document], {**row, "status": "Delinquent"}), [])
        finally:
            CURRENT.reset(token)

    def test_alaska_cycle_binding_allows_only_exact_repeated_ein(self):
        from deployment.state_snapshots import ak_selected_cycle_matches
        binding = dict(year=2024, ein="912155317", name="91-2155317", name_is_ein=True)
        def matches(b=binding, ein="912155317", name="Allen Institute", year=2024):
            return ak_selected_cycle_matches(b, ein, name, f"Registration Cycle: {year}")
        self.assertTrue(matches())
        self.assertFalse(matches(year=2025))
        self.assertFalse(matches(ein="912155318"))
        self.assertFalse(matches({**binding, "name": "91-2155318"}))
        self.assertFalse(matches({**binding, "name": "Allen Institute Foundation"}))
        self.assertTrue(matches({**binding, "name": "Allen Institute", "name_is_ein": False}))

    def test_alabama_unnumbered_original_only_for_exact_private_foundation_scope(self):
        from unittest.mock import patch
        from deployment.state_snapshots import al_scope_rows, attach_al_scope_original
        name = "Annie E. Casey Foundation"
        ein = "521951681"
        url = "https://ago.igovsolution.net/online/Lookups/Business.aspx"
        query = dict(state="AL", operation="search", name=name)
        record = dict(state="AL", ein=ein, organization_name=name)
        row = [name, "", "Active", "Private Foundation", "", "", "", "", "", "", ""]
        evidence = dict(query=query, complete=True, verification_pending=False, total=1, rows=[row],
                        headers=["Name", "License/Registration#", "Status", "Registration Type",
                                 "Issued Date", "Expiration Date", "Address", "City", "State", "Zip", "Print"])
        visible = f"Business Lookup Search Records: 1 to 1 of 1 {name} Active Private Foundation"
        match, = al_scope_rows(record, query, evidence, url, visible)
        self.assertFalse(al_scope_rows(record, query, evidence, url, visible.replace("Active", "Inactive")))
        self.assertFalse(al_scope_rows(record, query, {**evidence, "total": 2}, url, visible))
        self.assertFalse(al_scope_rows({**record, "organization_name": "Other Foundation"}, query, evidence, url, visible))
        ref = dict(state="AL", ein=ein, identifier=match[0], record_name=match[1],
                   operation="search", url="/state-snapshots/" + "a"*64 + ".pdf", captured_at=100)
        final = dict(state="AL", ein=ein, status="Needs Review", success=False)
        record.update(_al_scope_row=match, source_snapshots=[ref])
        with patch('deployment.state_snapshots.retain_references', return_value=[]):
            result = attach_al_scope_original(record, final)
            self.assertEqual(result['evidence_url'], ref['url'])
            self.assertFalse(result['success'])
            self.assertEqual(result['status'], 'Needs Review')
            self.assertEqual(attach_al_scope_original(record, {**final, 'status': 'Exempt'}).get('evidence_url'), None)

    def test_pennsylvania_first_timeout_preserves_usable_retry_in_original_budget(self):
        import json
        from unittest.mock import patch
        from deployment.state_snapshots import DEADLINE
        org = master.checker.Organization('Ford Foundation', '131684331')
        result = master.checker.StateResult(org.organization_name, org.ein, 'PA', 'Not Registered', '')
        result.success = True
        clock, requests = [0.0], []
        def fetch(url, deadline, **kwargs):
            requests.append((json.loads(kwargs['data'])['EntityName'], deadline, kwargs['request_timeout']))
            if len(requests) == 1:
                clock[0] += kwargs['request_timeout']
                raise TimeoutError('source response did not arrive')
            clock[0] += 5
            return b'{"Table":[],"Table1":[{"RESULTCOUNT":0}]}'
        deadline = DEADLINE.set(90)
        mode = master.LAB_LOOKUP_MODE_CONTEXT.set('standard')
        try:
            with patch.object(master, 'trial_identity', return_value=True), patch.object(master.time, 'monotonic', side_effect=lambda:clock[0]), patch.object(master.checker, 'search_pa', return_value=result), patch.object(master, 'pa_name_search_plan', return_value=['Ford Foundation']), patch.object(master, 'identity_fetch', side_effect=fetch):
                result = master.search_pa_with_name_fallback_core(None, org, lambda row:row)
            self.assertEqual(requests, [('Ford Foundation',15.0,7.0), ('Ford Foundation',15.0,8.0)])
            self.assertTrue(result._pa_api_attempts[0]['complete'])
            self.assertEqual(clock[0], 12)
        finally:
            master.LAB_LOOKUP_MODE_CONTEXT.reset(mode)
            DEADLINE.reset(deadline)
