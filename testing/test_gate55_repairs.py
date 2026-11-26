"""Recorded identities / synthetic edge contracts, plus actual defect pages.

These are offline tests, not seventy live registry adjudications per state.
"""
import ast, html, json, socket, subprocess, sys, unittest, io, time
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import registry_snapshot_server as c
from deployment import gate55_repairs as g, desktop_source_evidence as desktop, al_final_empty

ROOT=Path(__file__).resolve().parents[1]
F=ROOT/'testing/fixtures/gate55'
ROSTER=json.loads((F/'LOCAL-70.json').read_text())
RESULTS=[]

def old(name):
    src=subprocess.check_output(['git','show','5dea6c9:registry_snapshot_server.py'],cwd=ROOT)
    node=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)and n.name==name)
    space=dict(vars(c));exec(compile(ast.Module(body=[node],type_ignores=[]),'SK','exec'),space)
    return space[name]


class Gate55(unittest.TestCase):
    def test_tn_complete_contains_can_cover_reviewed_article_placement(self):
        from deployment.gate55_repairs import tn_contains_coverage_order
        names = ["The Jed Foundation", "JED FOUNDATION", "Jed Foundation (The)"]
        self.assertEqual(tn_contains_coverage_order(names), [names[1], names[0], names[2]])
        distinct = [*names, "Jed Research Institute"]
        self.assertEqual(tn_contains_coverage_order(distinct), distinct)

    def setUp(self):
        self.net=patch.object(socket.socket,'connect',side_effect=AssertionError('Offline network forbidden'));self.net.start()
    def tearDown(self):self.net.stop()

    def test_FL_original_blank_date_pages(self):
        before=old('fl_business_candidate_rows')
        for name,ident in [('ITHACA','CH32432'),('KENYON','CH44426')]:
            body=(F/f'FL-{name}.html').read_text(encoding='utf-8')
            self.assertEqual(before(body),[])
            rows=c.fl_business_candidate_rows(body);self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['business_evidence']['identifier'],ident)
            self.assertIn('Status Law NA - Educational',rows[0]['text'])
            self.assertNotIn('Expiration Date',rows[0]['text'])

    def test_FL_70_date_and_status_boundaries(self):
        before=old('fl_business_candidate_rows');template=(F/'FL-ITHACA.html').read_text(encoding='utf-8')
        for case in ROSTER:
            body=template.replace('ITHACA COLLEGE',html.escape(case['name']))
            self.assertEqual(len(c.fl_business_candidate_rows(body)),1)
            for raw in ['Active','Expired','Suspended','Unrecognized','Law NA - Religious']:
                changed=body.replace('Law NA - Educational',raw)
                self.assertEqual(c.fl_business_candidate_rows(changed),before(changed))
            self.assertEqual(c.fl_business_candidate_rows(body.replace('</html>','')),[])
            RESULTS.append(dict(state='FL',**case,passed=True,scenario='explicit educational / absent dates; five other statuses unchanged'))

    def test_FL_70_complete_business_route_without_expiration(self):
        template=(F/'FL-ITHACA.html').read_text(encoding='utf-8')
        for case in ROSTER:
            rows=c.fl_business_candidate_rows(template.replace('ITHACA COLLEGE',html.escape(case['name'])))
            org=c.checker.Organization(case['name'],case['ein'])
            with patch.object(c,'trial_identity',return_value=True), patch.object(c,'fl_business_lookup_enabled',return_value=True), patch.object(c,'fl_business_public_rows',return_value=rows), patch.object(c,'CAPTURE_EVIDENCE_SCREENSHOTS',False), patch.object(c,'CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False), patch.object(c,'fl_reviewed_alias_address',return_value=None):
                result=c.search_fl_with_transport(NS(),org,NS())
            if result.success:
                self.assertEqual(result.status,'Exempt')
                self.assertEqual(result.matched_registry_identifier,'CH32432')
                self.assertEqual(result._cc_registration_date_evidence['initial'],'')
            else:
                # Complex DBA identity guard remains authoritative; the new
                # date exemption must never turn its refusal into approval.
                self.assertIn(result.status,['Unable to Confirm','Needs Review'])
                self.assertFalse(result.matched_registry_identifier)
        for name,ein in [('ITHACA','150532204'),('KENYON','314379507')]:
            rows=c.fl_business_candidate_rows((F/f'FL-{name}.html').read_text(encoding='utf-8'))
            with patch.object(c,'trial_identity',return_value=True), patch.object(c,'fl_business_lookup_enabled',return_value=True), patch.object(c,'fl_business_public_rows',return_value=rows), patch.object(c,'CAPTURE_EVIDENCE_SCREENSHOTS',False), patch.object(c,'CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False), patch.object(c,'fl_reviewed_alias_address',return_value=None):
                result=c.search_fl_with_transport(NS(),c.checker.Organization(name+' COLLEGE',ein),NS())
            self.assertTrue(result.success);self.assertEqual(result.status,'Exempt')

    def test_CT_70_parent_candidate_is_not_identity_approval(self):
        for i,case in enumerate(ROSTER):
            name=case['name'];base=c.normalized_match_name(name)
            source=name+' (REGISTRY SPELLING) INC'
            keep=g.ct_parenthetical_candidate(source,[name],c.normalized_match_name)
            self.assertEqual(keep,len(base.split())>=3)
            for other in ['UNRELATED ORGANIZATION','SOME OTHER FOUNDATION']:
                self.assertFalse(g.ct_parenthetical_candidate(other+' (REGISTRY SPELLING) INC',[name],c.normalized_match_name))
            self.assertFalse(g.ct_parenthetical_candidate(name+' California Affiliate',[name],c.normalized_match_name))
            RESULTS.append(dict(state='CT',**case,passed=True,scenario='candidate retention only; unrelated parent/affiliate rejected'))

    def test_CT_actual_variant_requires_matching_EIN_or_office(self):
        name='Jewish National Fund';org=c.checker.Organization(name,'131659627')
        row='<b class="headline6">JEWISH NATIONAL FUND (KAREN KAYMETH LEISREAL) INC</b><b>Credential</b><p>CHR.0001673</p><b>Credential Description</b><p>PUBLIC CHARITY</p><b>Status</b><p>ACTIVE</p>'
        for ein in ['131659627','999999999','']:
            with patch.object(c,'trial_identity',return_value=True),patch.object(c,'known_names_for_ein',return_value=[name]),patch.object(c,'ct_direct_detail_text',return_value='EIN: '+ein),patch.object(c,'is_reviewed_alias',return_value=False):
                result,_=c.ct_direct_result_from_row(org,row,[name],'https://www.elicense.ct.gov/')
            if ein=='999999999':self.assertIsNone(result)
            elif ein:self.assertTrue(result.success);self.assertNotEqual(result.status,'Needs Review')
            else:self.assertFalse(result.success);self.assertTrue(result._cc_identity_review)

    def test_WI_actual_successful_query_reaches_actual_selected_record(self):
        name="JEWISH BOARD OF FAMILY & CHILDREN'S SERVICES, INC"
        aliases=[name,"JEWISH BOARD OF FAMILY AND CHILDREN'S SERVICES, INC.",'Jewish Board of Family & Children Services, Inc.']
        org=c.checker.Organization(name,'135564937')
        token=c.REVIEWED_NAME_CONTEXT.set({'135564937':tuple(aliases)})
        try:
            with patch.object(c,'known_names_for_ein',return_value=aliases):plan=c.wi_direct_search_names(org)
            positive=(F/'WI-JEWISH-BOARD.html').read_text(encoding='utf-8')
            empty='<html>There are no query results</html>'
            attempted=[]
            def response(open_,request,**kwargs):
                query=parse_qs(urlsplit(request.full_url).query)['FirmName'][0];attempted.append(query)
                return positive if query=="JEWISH BOARD OF FAMILY AND CHILDREN'S SERVICES INC" else empty
            opener=NS(open=lambda *a,**k:io.BytesIO(b'<html></html>'))
            with patch.object(c,'wi_request_opener',return_value=opener),patch('deployment.wi_query_history.read_wi_response',side_effect=response):
                selected,reached=c.wi_http_search_best_match(plan,[name,*aliases],deadline=time.perf_counter()+15,original_name=name,ein=org.ein)
            self.assertTrue(reached);self.assertIsNotNone(selected)
            self.assertEqual(selected['license_number'],'20308-800')
            self.assertEqual(attempted[1],"JEWISH BOARD OF FAMILY AND CHILDREN'S SERVICES INC")
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_WI_70_full_required_plan_still_has_delimiter_recovery(self):
        for case in ROSTER:
            plan=[case['name']+', INC',case['name']+" CHILDREN'S SERVICES, INC."]
            out=g.wi_delimiter_variants(plan,plan)
            self.assertEqual(out[0],plan[0])
            self.assertEqual(len(out),len(plan)+1)
            self.assertTrue(set(plan)<=set(out))
            self.assertIn(case['name']+" CHILDREN'S SERVICES INC",out)
            self.assertEqual(len(set(out)),len(out))
        name="JEWISH BOARD OF FAMILY & CHILDREN'S SERVICES, INC"
        aliases=[name,"JEWISH BOARD OF FAMILY AND CHILDREN'S SERVICES, INC.",'Jewish Board of Family & Children Services, Inc.']
        token=c.REVIEWED_NAME_CONTEXT.set({'135564937':tuple(aliases)})
        try:
            with patch.object(c,'known_names_for_ein',return_value=aliases):
                plan=c.wi_direct_search_names(c.checker.Organization(name,'135564937'))
            self.assertIn("JEWISH BOARD OF FAMILY AND CHILDREN'S SERVICES INC",plan)
            self.assertEqual(plan[1],"JEWISH BOARD OF FAMILY AND CHILDREN'S SERVICES INC")
            self.assertTrue(set(aliases[:2])<=set(plan))
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_WI_70_literal_variants_preserve_apostrophes_and_budget(self):
        for case in ROSTER:
            n=case['name'];plan=[n+", INC",n+" CHILDREN'S SERVICES, INC.",n+' Other Identity',n+' Optional fragment']
            new=g.wi_delimiter_variants(plan,plan[:3])
            self.assertEqual(new[0],plan[0]);self.assertIn(n+" CHILDREN'S SERVICES INC",new)
            self.assertIn(n+' Other Identity',new);self.assertLessEqual(len(new),len(plan))
            self.assertEqual(g.wi_delimiter_variants(new,plan[:3]),new)
            RESULTS.append(dict(state='WI',**case,passed=True,scenario='comma removal without apostrophe loss / no additional queries'))

    def test_AK_70_completed_recent_years_stop_only_proven_repeats(self):
        current=c.ak_latest_registration_cycle();years=list(range(current,min(current,c.AK_RECENT_FILING_CUTOFF_YEAR)-1,-1))
        for case in ROSTER:
            result=dict(state='AK',ein=case['ein'],success=True,status='Delinquent',reason_code='MATCH_EIN_EXACT',matched_registry_name=case['name'],matched_registry_identifier=case['ein'],raw_status_text='Registration Cycle: 2019',ak_ein_year_evidence=dict(schema=1,ein=case['ein'],expected_recent_years=years,completed_years=years))
            self.assertTrue(g.ak_completed_recent_ein_years(c,result))
            for proof in [dict(result['ak_ein_year_evidence'],ein='999999999'),dict(result['ak_ein_year_evidence'],completed_years=years[1:]),dict(result['ak_ein_year_evidence'],expected_recent_years=[2019])]:
                self.assertFalse(g.ak_completed_recent_ein_years(c,dict(result,ak_ein_year_evidence=proof)))
            calls=[]
            with patch.object(c,'run_state_lookup',side_effect=lambda *a,**kw:(calls.append(a)or dict(result))),patch.object(c,'trial_identity',return_value=None):
                final=c._run_single_state_lookup_reliably_core(case['name'],case['ein'],'AK')
            self.assertEqual(len(calls),1);self.assertEqual(final['status'],'Delinquent')
            RESULTS.append(dict(state='AK',**case,passed=True,scenario='completed recent EIN years stop repeated whole lookup; incomplete/foreign proof rejected'))

    def test_TN_70_coverage_order_preserves_all_names(self):
        for case in ROSTER:
            n=case['name'];plan=[n+' (LEGAL NAME)',n+' (VARIANT ONE)',n+' (VARIANT TWO)',n]
            new=g.tn_contains_coverage_order(plan)
            self.assertEqual(new[0],plan[0]);self.assertEqual(set(new),set(plan));self.assertEqual(len(new),len(plan))
            if len(n.split())>=3 and '('not in n:self.assertEqual(new[1],n)
            self.assertEqual(g.tn_contains_coverage_order(new),new)
            RESULTS.append(dict(state='TN',**case,passed=True,scenario='same existing reviewed names / original first / complete literal coverage unchanged'))

    def test_WI_negative_has_no_new_source_capture_request(self):
        for case in ROSTER:
            run=NS(state='WI',ein=case['ein'],source_search_hint={'url':'unused','name':case['name']})
            self.assertIsNone(desktop.retained_request(run,dict(state='WI',ein=case['ein'],status='Not Registered',success=True)))

    def test_AL_70_completed_negatives_keep_original_response(self):
        for case in ROSTER:
            response={'phase':'complete','result':dict(state='AL',ein=case['ein'],status='Not Registered',queries_attempted=[case['name']])}
            self.assertIs(al_final_empty.prepare(None,dict(state='AL'),response),response)
            RESULTS.append(dict(state='AL',**case,passed=True,scenario='settled negative keeps search history; zero image continuation'))


if __name__=='__main__':
    assert len(ROSTER)==len({r['ein']for r in ROSTER})==70
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gate55)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (ROOT/'testing/gate55-local-results.json').write_text(json.dumps({'passed':result.wasSuccessful(),'methods':result.testsRun,'cases':RESULTS,'kind':'offline recorded identities with synthetic conditions; original FL pages separate'},indent=2))
    sys.exit(not result.wasSuccessful())
