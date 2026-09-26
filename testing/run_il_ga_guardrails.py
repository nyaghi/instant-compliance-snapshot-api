"""IL/GA source-shape controls; these do not establish live transport readiness."""
import sys, unittest, copy, time, re, ast, subprocess
from unittest.mock import patch
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as cc

class RedundantAcronymIdentityTests(unittest.TestCase):
    def test_legal_suffix_before_verified_acronym_preserves_identity(self):
        match = cc.score_candidate('Reading Is Fundamental, Inc.', '52-0976257', {'name': 'Reading Is Fundamental, Inc. (RIF)'})
        self.assertEqual(match['decision'], 'accepted')
        self.assertEqual(match['reason'], 'MATCH_REDUNDANT_BRACKET_ACRONYM')

    def test_acronym_does_not_erase_chapter_or_wrong_ein(self):
        for candidate in ['Reading Is Fundamental Georgia, Inc. (RIF)', 'Reading Is Fundamental, Inc. (RFI)', 'Reading Is Fundamental, Inc. (RIF) Georgia']:
            with self.subTest(candidate=candidate):
                self.assertNotEqual(cc.score_candidate('Reading Is Fundamental, Inc.', '52-0976257', {'name':candidate})['decision'], 'accepted')
        self.assertEqual(cc.score_candidate('Reading Is Fundamental, Inc.', '52-0976257', {'name':'Reading Is Fundamental, Inc. (RIF)', 'ein':'36-2170141'})['reason'], 'REJECT_DIFFERENT_EIN')

IL = """FEEDING AMERICA
161 N. CLARK STREET, SUITE 700
CHICAGO, IL 60601
Status: Good Standing
CO Number: 01015532
FEIN: 363673599
Registration Date: 08/27/1985
Annual Report Due Date: 12/31/2026
Annual Financials (5)
06/30/2025
"""

def ga_html(**changes):
    values = dict(full_name='Make-A-Wish Foundation Of America', license_no='CH003977',
                  profession='Charities', license_type='Charity', status='Active',
                  expiry='3/20/2027', issue_date='', last_ren='')
    values.update(changes)
    return ''.join(f'<span id="_ctl34__ctl1_{k}">{v}</span>' for k,v in values.items()) + (
        '<div id="more_details"><span id="_ctl52__ctl1_license_no">PS005211</span>'
        '<span id="_ctl52__ctl1_status">Revoked</span>'
        '<span id="_ctl52__ctl1_full_name">Unrelated Solicitor</span></div>')

class SourceControls(unittest.TestCase):
    def test_il_source_identity_and_actual_deadline(self):
        r=cc.il_charity_detail_text(IL,'01015532')
        self.assertEqual(r['ein'],'363673599')
        self.assertEqual(r['expiration'],date(2026,12,31))
        self.assertEqual(r['initial'],date(1985,8,27))
    def test_il_wrong_selected_record_rejected(self):
        with self.assertRaises(ValueError):cc.il_charity_detail_text(IL,'01015533')
    def test_il_incomplete_identity_rejected(self):
        with self.assertRaises(ValueError):cc.il_charity_detail_text(IL.replace('FEIN: 363673599','FEIN:'))
    def test_il_malformed_date_rejected(self):
        with self.assertRaises(ValueError):cc.il_charity_detail_text(IL.replace('12/31/2026','unknown'))
    def test_il_missing_and_blank_due_dates_are_incomplete_not_current(self):
        for body in [IL.replace('12/31/2026',''),IL.replace('Annual Report Due Date: 12/31/2026\n','')]:
            parsed=cc.il_charity_detail_text(body,'01015532')
            self.assertEqual(parsed['status'],'Unable to Confirm')
            self.assertEqual(parsed['ein'],'363673599')
            self.assertIsNone(parsed['expiration'])
    def test_il_duplicate_due_labels_rejected(self):
        with self.assertRaises(ValueError):cc.il_charity_detail_text(IL+'\nAnnual Report Due Date: 12/31/2027')
    def test_il_unknown_status_not_current(self):
        self.assertEqual(cc.il_charity_detail_text(IL.replace('Good Standing','Unrecognized'))['status'],'Unable to Confirm')
    def test_ga_associated_licenses_not_used(self):
        r=cc.ga_charity_detail_html(ga_html(),'CH003977')
        self.assertEqual(r['identifier'],'CH003977');self.assertEqual(r['raw_status'],'Active')
        self.assertEqual(r['expiration'],date(2027,3,20));self.assertEqual(r['aliases'],[])
        self.assertIsNone(r['initial']);self.assertIsNone(r['renewal'])
    def test_ga_wrong_record_rejected(self):
        with self.assertRaises(ValueError):cc.ga_charity_detail_html(ga_html(),'CH002707')
    def test_ga_solicitor_rejected(self):
        with self.assertRaises(ValueError):cc.ga_charity_detail_html(ga_html(license_type='Paid Solicitor'),'CH003977')
    def test_ga_lapsed_adverse_precedes_future_date(self):
        self.assertEqual(cc.ga_charity_detail_html(ga_html(status='Lapsed'),'CH003977')['status'],'Delinquent')
    def test_ga_terminated_not_active(self):
        self.assertEqual(cc.ga_charity_detail_html(ga_html(status='Registration Terminated'),'CH003977')['status'],'Closed / Withdrawn / Canceled')
    def test_ga_malformed_date_rejected(self):
        with self.assertRaises(ValueError):cc.ga_charity_detail_html(ga_html(expiry='invalid'),'CH003977')
    def test_block_page_cannot_be_parsed_as_negative(self):
        with self.assertRaises(ValueError):cc.ga_charity_detail_html('Performing security verification','CH003977')
        with self.assertRaises(ValueError):cc.il_charity_detail_text('No Records Available')


def search_row(name='FEEDING AMERICA',identifier='01015532',key=''):
    return dict(name=name,identifier=identifier,detail_key=key,location='',street='',region='',postal_code='')


class IntegrationControls(unittest.TestCase):
    def setUp(self):
        self.org=cc.checker.Organization('Feeding America','36-3673599')
        p=patch.object(cc,'reconciled_registry_address',return_value={'decision':'not_available'});p.start();self.addCleanup(p.stop)
        p=patch.object(cc,'known_names_for_ein',return_value=[]);p.start();self.addCleanup(p.stop)
    def test_il_exact_ein_overrides_agent_address(self):
        row={**search_row(),**cc.il_charity_detail_text(IL)}
        with patch.object(cc,'reconciled_registry_address',side_effect=AssertionError('agent address must not veto exact EIN')):
            self.assertEqual(cc.licensed_charity_identity(self.org,row,'IL',time.monotonic()+5),'accepted')
    def test_il_ein_first_and_only_then_names(self):
        queries=[]
        def evidence(q):
            queries.append(q)
            return {'body':IL} if 'identifier' in q else {'rows':[search_row()]}
        result=cc.il_ga_browser_lookup(self.org,'IL',evidence)
        self.assertEqual(queries,[{'state':'IL','ein':'363673599'},{'state':'IL','identifier':'01015532'}])
        self.assertEqual(result.matched_registry_identifier,'01015532')
        self.assertIn('annual-report due date',result.source_note)
        self.assertNotIn('does not display an EIN',result.source_note)
    def test_il_completed_empty_uses_combined_label(self):
        queries=[]
        def evidence(q):queries.append(q);return {'rows':[]}
        result=cc.il_ga_browser_lookup(self.org,'IL',evidence)
        self.assertEqual(queries[0],{'state':'IL','ein':'363673599'})
        self.assertTrue(any('orgName' in q for q in queries))
        self.assertEqual(cc.public_status(result),'Not Registered / Non-Compliant')
        data=cc.response_data_for_lookup(result,'',self.org,self.org.organization_name,self.org.ein,'IL',time.perf_counter())
        self.assertEqual(data['status'],'Not Registered / Non-Compliant')
        self.assertIn('does not distinguish',data['comments'])
        self.assertNotIn('Registry match',data['comments'])
        self.assertEqual(data['matched_registry_name'],'')
        self.assertEqual(data['matched_registry_identifier'],'')
    def test_il_loaded_missing_due_preserves_identity_and_explains_missing_date(self):
        for body in [IL.replace('12/31/2026',''),IL.replace('Annual Report Due Date: 12/31/2026\n','')]:
            def evidence(q):return {'body':body} if 'identifier' in q else {'rows':[search_row()]}
            result=cc.il_ga_browser_lookup(self.org,'IL',evidence)
            self.assertEqual(result.status,'Unable to Confirm')
            self.assertEqual(result.matched_registry_identifier,'01015532')
            self.assertIn('record loaded',result.source_note)
            self.assertNotIn('retry',result.source_note.lower())
    def test_il_detail_failures_have_distinct_non_negative_explanations(self):
        record=dict(state='IL',organization_name='Feeding America',ein='36-3673599')
        for code,phrase in [('NOT_OPENED','did not open'),('BLANK','no readable'),('IDENTITY_INCOMPLETE','could not be confirmed')]:
            result=cc.il_ga_connector_failure(record,'NY_CONNECTOR_IL_DETAIL_'+code)
            self.assertEqual(result['status'],'Unable to Confirm')
            self.assertIn(phrase,result['comments'])
    def test_il_incomplete_fallback_never_negative(self):
        def evidence(q):
            if 'ein' in q:return {'rows':[]}
            raise TimeoutError()
        with self.assertRaises(TimeoutError):cc.il_ga_browser_lookup(self.org,'IL',evidence)
    def test_il_wrong_ein_not_discovered(self):
        def evidence(q):return {'body':IL.replace('363673599','123456789')} if 'identifier' in q else {'rows':[search_row()]}
        self.assertEqual(cc.il_ga_browser_lookup(self.org,'IL',evidence,'identity')['names'],[])
    def test_il_ein_bound_discovery(self):
        def evidence(q):return {'body':IL} if 'identifier' in q else {'rows':[search_row()]}
        names=cc.il_ga_browser_lookup(self.org,'IL',evidence,'identity')['names']
        self.assertEqual([r['name'] for r in names],['FEEDING AMERICA'])
        self.assertTrue(names[0]['verified'])
    def test_ga_active_selected_after_terminated_and_chapter_rejected(self):
        org=cc.checker.Organization('Make-A-Wish Foundation Of America','86-0481941')
        keys=['430cb135-998f-4d66-8560-4bd50a8d0040','c98044f6-f1fe-45ca-9c5a-766560e631e6','573f1092-88a5-4129-9884-e852a954f86b']
        rows=[search_row(org.organization_name,'CH002707',keys[0]),search_row(org.organization_name,'CH003977',keys[1]),search_row('Make-A-Wish Foundation Of East Tennessee/north Georgia','CH002301',keys[2])]
        requested=[]
        def evidence(q):
            requested.append(q)
            if 'identifier' not in q:return {'rows':rows}
            name=next(r['name'] for r in rows if r['identifier']==q['identifier'])
            return {'body':ga_html(full_name=name,license_no=q['identifier'],status='Active' if q['identifier']=='CH003977' else 'Registration Terminated')}
        result=cc.il_ga_browser_lookup(org,'GA',evidence)
        self.assertEqual(result.matched_registry_identifier,'CH003977')
        self.assertNotEqual(result.matched_registry_identifier,'CH002301')
        self.assertIn('Other returned records',result.source_note)
    def test_ga_empty_is_not_registered_not_il_label(self):
        result=cc.il_ga_browser_lookup(self.org,'GA',lambda q:{'rows':[]})
        self.assertEqual(cc.public_status(result),'Not Registered')
    def test_ga_qualified_name_without_address_stays_visible_for_review(self):
        org=cc.checker.Organization('Young Life','84-0385934')
        row=search_row('Young Life (of Texas)','CH000861','85f78478-2813-4bd9-b1f0-8d49aa062631')
        def evidence(query):
            if 'identifier' not in query:return {'rows':[row]}
            return {'body':ga_html(full_name=row['name'],license_no=row['identifier'],status='Exempt',expiry='4/14/2019')}
        result=cc.il_ga_browser_lookup(org,'GA',evidence)
        self.assertEqual(result.status,'Needs Review')
        self.assertIn('Young Life (of Texas)',result.source_note)
        self.assertNotEqual(result.status,'Not Registered')
    def test_ga_exempt_license_type(self):
        self.assertEqual(cc.ga_charity_detail_html(ga_html(license_type='Exempt Charity'),'CH003977')['status'],'Exempt')
    def test_detail_record_change_rejected(self):
        def evidence(q):return {'body':IL.replace('FEEDING AMERICA','DIFFERENT ORGANIZATION')} if 'identifier' in q else {'rows':[search_row()]}
        with self.assertRaises(ValueError):cc.il_ga_browser_lookup(self.org,'IL',evidence)
    def test_completeness_query_total_and_duplicates_required(self):
        q={'state':'IL','ein':'363673599'}
        good={'query':q,'complete':True,'total':1,'rows':[search_row()]}
        self.assertEqual(len(cc.il_ga_clean_evidence(good,q)['rows']),1)
        for change in [{'complete':False},{'total':2},{'query':{'state':'IL','ein':'123456789'}},{'total':2,'rows':[search_row(),search_row()]}]:
            with self.assertRaises(ValueError):cc.il_ga_clean_evidence({**good,**change},q)
    def test_detail_mismatch_and_unbounded_body_rejected(self):
        q={'state':'IL','identifier':'01015533'}
        with self.assertRaises(ValueError):cc.il_ga_clean_evidence({'query':q,'complete':True,'body':IL},q)
        with self.assertRaises(ValueError):cc.il_ga_clean_evidence({'query':q,'complete':True,'body':'x'*60001},q)
    def test_timeout_failure_is_inconclusive(self):
        for state in ['IL','GA']:
            result=cc.il_ga_connector_failure({'state':state,'ein':self.org.ein,'organization_name':self.org.organization_name})
            self.assertEqual(result['status'],'Unable to Confirm');self.assertFalse(result['success'])
    def test_reviewed_names_all_searched_before_generated(self):
        queries=[]
        with patch.object(cc,'known_names_for_ein',return_value=['Former Food Network','Food for Everyone']):
            def evidence(q):queries.append(q);return {'rows':[]}
            cc.il_ga_browser_lookup(self.org,'GA',evidence)
        self.assertEqual([q['orgName'] for q in queries[:3]],['Feeding America','Former Food Network','Food for Everyone'])
    def test_original_32_lane_indices_preserved_and_ui_34(self):
        root=Path(__file__).resolve().parents[1]
        previous=subprocess.check_output(['git','show','35e61ae:registry_snapshot_server.py'],cwd=root).decode('utf-8')
        tree=ast.parse(previous)
        states=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SUPPORTED_STATES' for t in n.targets))
        self.assertEqual(cc.SUPPORTED_STATES[:32],states)
        self.assertEqual(cc.SUPPORTED_STATES[32:],['IL','GA'])
        ui=(root/'web-staging/index.html').read_text(encoding='utf-8')
        self.assertEqual(set(re.findall(r'name="states" value="([A-Z]{2})"',ui)),set(cc.SUPPORTED_STATES))
    def test_report_preserves_combined_status_and_no_record_evidence(self):
        import charity_clarity_report as report
        row={'state':'IL','status':'Not Registered / Non-Compliant','comments':'Illinois note: Illinois lists compliant charities.'}
        finding=report.report_findings([row])[0]
        self.assertEqual(finding['label'],row['status']);self.assertIsNone(finding['bucket'])
        self.assertIn('non-compliance',report.verification_needed(row))
        self.assertEqual(report.summary_groups([finding]),[('Not registered / non-compliant (Illinois)',['IL'])])
        self.assertEqual(report.action_items([row])[0][0],'Resolve the Illinois compliant-directory gap')
    def test_split_pill_uses_existing_status_colors(self):
        ui=(Path(__file__).resolve().parents[1]/'web-staging/index.html').read_text()
        self.assertIn('linear-gradient(90deg, #cbd5e1 0%, #cbd5e1 50%, #fca5a5 50%, #fca5a5 100%)',ui)
        self.assertIn('if (normalized === "not registered / non-compliant") return "status-il-combined"',ui)
    def test_mature_state_functions_unchanged_from_09245(self):
        root=Path(__file__).resolve().parents[1]
        previous=subprocess.check_output(['git','show','35e61ae:registry_snapshot_server.py'],cwd=root).decode('utf-8')
        functions=lambda source:{n.name:ast.dump(n) for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)}
        old,new=functions(previous),functions((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        changed={k for k in old if old[k]!=new.get(k)}
        self.assertEqual(changed,{'public_status','identity_rows_names','licensed_charity_identity','registration_date_metadata',
            'true_status_from_body','comments_for_result_base','run_state_lookup','ny_connector_failure',
            'ny_connector_clean_response','ny_connector_advance','ny_connector_request','normalize_registry_match_fields',
            # Shared verified-acronym fix covered above and by release regression.
            'redundant_bracket_acronym_key'})


if __name__=='__main__':unittest.main()


