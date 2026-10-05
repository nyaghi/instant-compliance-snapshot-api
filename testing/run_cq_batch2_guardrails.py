"""October 5 CQ failures and independent adverse controls; offline fixtures only."""
import sys, unittest, ast, subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
from testing.run_final_four_source_guardrails import NC, NC_PROFILE


class MississippiReadiness(unittest.TestCase):
    def run_form(self,responses,inputs,body='Temporarily loading'):
        page=Mock();page.goto.side_effect=[SimpleNamespace(status=x) for x in responses]
        page.locator.return_value.inner_text.return_value=body
        module=c.state_batch_modules(['MS'])[c.load_state_batch_bundle().STATE_TO_MODULE['MS']]
        with patch.object(c,'ms_ready_search_input',side_effect=inputs) as ready, \
             patch.object(c,'safe_wait_for_network_idle'), \
             patch.object(c,'ms_wait_for_search_results',return_value=(None,True,'')):
            result=c.search_ms_fast(page,module.Organization(organization_name='Example Relief'))
        return result,page,ready

    def test_one_bounded_form_recovery_can_finish(self):
        result,page,_=self.run_form([200,200],[None,Mock()])
        self.assertTrue(result.success);self.assertEqual(page.goto.call_count,2)

    def test_access_rejection_does_not_retry_or_claim_absence(self):
        for status in [403,429,500,503]:
            result,page,ready=self.run_form([status],[])
            self.assertFalse(result.success);self.assertEqual(page.goto.call_count,1)
            ready.assert_not_called();self.assertEqual(result.source_confidence,'incomplete_search')

    def test_verification_is_not_retried_or_reported_as_no_record(self):
        result,page,_=self.run_form([200],[None],'Security verification: verify you are human')
        self.assertFalse(result.success);self.assertEqual(page.goto.call_count,1)

    def test_missing_form_keeps_diagnostic_and_bounded_attempts(self):
        result,page,_=self.run_form([200,200],[None,None],'Maintenance')
        self.assertFalse(result.success);self.assertEqual(page.goto.call_count,2)
        self.assertEqual(len(result.source_attempts),2)
        self.assertNotIn('Exact status taken',result.source_note)


class VirginiaIdentity(unittest.TestCase):
    def test_related_foundation_is_not_the_requested_institution(self):
        for primary in ['College of William & Mary', 'Example Valley Hospital', 'Eastern Arts University']:
            with self.subTest(primary=primary):
                org=c.checker.Organization(primary,'123456789')
                self.assertFalse(c.va_evoke_entity_matches_request({'name':primary+' Foundation'},org,True))

    def test_exact_foundation_and_generated_punctuation_remain_valid(self):
        for name,candidate in [('Example Valley Hospital Foundation','Example Valley Hospital Foundation, Inc.'),
                               ('College of William & Mary','COLLEGE OF WILLIAM AND MARY')]:
            self.assertTrue(c.va_evoke_entity_matches_request({'name':candidate},c.checker.Organization(name,'123456789'),True))

    def test_candidate_ein_conflict_cannot_be_overruled_by_exact_name(self):
        org=c.checker.Organization('Example Relief','123456789')
        self.assertFalse(c.va_evoke_entity_matches_request({'name':org.organization_name,'ein':'987654321'},org,True))
        self.assertTrue(c.va_evoke_entity_matches_request({'name':'Different legal name','ein':org.ein},org,False))

    def test_reviewed_full_identity_still_works(self):
        org=c.checker.Organization('Example Arts College','123456789')
        token=c.REVIEWED_NAME_CONTEXT.set({'123456789':('Example Arts College Foundation',)})
        try:self.assertTrue(c.va_evoke_entity_matches_request({'name':'Example Arts College Foundation'},org,True))
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)


class OklahomaRecency(unittest.TestCase):
    def run_records(self, statuses, histories):
        org=c.checker.Organization('Example Relief','123456789')
        org.ok_equivalent_records=[('Example Relief','4311111111'),('Example Relief, Inc.','4322222222')]
        page=Mock()
        def goto(url,**kwargs):page.url=url;return SimpleNamespace(status=200)
        page.goto.side_effect=goto
        page.locator.return_value.count.return_value=0
        texts=[f'Entity Name: {name}\nStatus: {status}\nFILING HISTORY :\n{history}'
               for (name,_),status,history in zip(org.ok_equivalent_records,statuses,histories)]
        module=c.state_batch_modules(['OK'])[c.load_state_batch_bundle().STATE_TO_MODULE['OK']]
        with patch.object(c,'trial_identity',return_value={'origin':'fixture'}),patch.object(module,'body_text',side_effect=texts):
            return c.ok_open_latest_equivalent_detail(page,org,module,(450,None,'Example Relief','4311111111'))

    def test_newer_cancellation_without_renewal_is_not_a_transport_failure(self):
        result=self.run_records(['Cancelled','Expired'],[
            '52991120001 Notice of Registration Exemption February 11, 2022 5\n54912020001 Notice of Cancellation June 3, 2022 2',
            '50234420002 Application for Registration July 13, 2021 5'])
        self.assertEqual(result[1],'4311111111')

    def test_newer_active_registration_supersedes_old_cancellation(self):
        result=self.run_records(['Cancelled','In Existence'],[
            '54912020001 Notice of Cancellation June 3, 2022 2',
            '50234420002 Renewal Registration July 13, 2026 5'])
        self.assertEqual(result[1],'4322222222')

    def test_missing_terminal_event_date_is_not_guessed(self):
        with self.assertRaises(TimeoutError):self.run_records(['Cancelled','Expired'],[
            '54912020001 Notice of Cancellation',
            '50234420002 Application for Registration July 13, 2021 5'])

    def test_unrelated_late_document_does_not_establish_renewal(self):
        with self.assertRaises(TimeoutError):self.run_records(['In Existence','Expired'],[
            '54912020001 Change of Registered Agent June 3, 2026 2',
            '50234420002 Application for Registration July 13, 2021 5'])


class NorthCarolinaCompletion(unittest.TestCase):
    def lookup(self,aliases=(),missing_alias=False,no_primary=False):
        name='Federation of Jewish Communities of the CIS, Inc.'
        org=c.checker.Organization(name,'133970940');calls=[]
        def source(q):
            calls.append(q)
            if q['operation']=='search':
                if q['name']=='Reviewed Former Name':
                    if missing_alias:raise TimeoutError('Required alias unavailable')
                    return {'state':'NC','query':q,'complete':True,'verification_pending':False,'total':0,'rows':[]}
                if q['name']!=name:raise AssertionError('Unnecessary generated search')
                row={**NC,'CSL Legal Name':name,'License':'SL017200','Status':'Expired License',
                     'Expiration Date':'6/15/2026','Extension End Date':''}
                return {'state':'NC','query':q,'complete':True,'verification_pending':False,
                        'total':0 if no_primary else 1,'rows':[] if no_primary else [row]}
            return {'state':'NC','query':q,'complete':True,'verification_pending':False,
                    'fields':{**NC_PROFILE,'Name':name,'Registration #':'SL017200','Status':'Expired License',
                              'Expiration Date':'6/15/2026','Extension End Date':''}}
        with patch.object(c,'trial_identity',return_value={'origin':'fixture'}), \
             patch.object(c,'licensed_charity_names',return_value=([name,*aliases],['Federation of Jewish'])), \
             patch.object(c,'reconciled_registry_address',return_value={'decision':'not_available'}):
            result=c.final_four_browser_lookup(org,'NC',source)
        return result,calls

    def test_confirmed_expired_profile_does_not_need_generated_fallback(self):
        result,calls=self.lookup()
        self.assertEqual(result.status,'Delinquent');self.assertTrue(result.success)
        self.assertEqual(len(calls),2)

    def test_all_reviewed_aliases_are_still_searched_before_adverse_finish(self):
        result,calls=self.lookup(['Reviewed Former Name'])
        self.assertEqual(result.status,'Delinquent')
        self.assertEqual([q['name'] for q in calls if q['operation']=='search'],[
            'Federation of Jewish Communities of the CIS, Inc.','Reviewed Former Name'])

    def test_missing_reviewed_alias_cannot_be_hidden(self):
        with self.assertRaisesRegex(TimeoutError,'Required alias'):self.lookup(['Reviewed Former Name'],True)

    def test_no_match_still_tries_generated_name(self):
        with self.assertRaisesRegex(AssertionError,'Unnecessary generated'):self.lookup(no_primary=True)


class CurrentReleaseScope(unittest.TestCase):
    def test_unrelated_code_and_budgets_equal_deployed_cq(self):
        root=Path(__file__).resolve().parents[1]
        before=ast.parse(subprocess.check_output(['git','show','9a3d3ccebca6a4119e665eb6c1323de6b2acc337:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        after=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        allowed={'final_four_browser_lookup','va_evoke_entity_matches_request','ok_open_latest_equivalent_detail',
                 'search_ms_fast','ms_ready_search_input'}
        for tree in (before,after):
            tree.body=[node for node in tree.body if not (isinstance(node,ast.FunctionDef) and node.name in allowed)]
        self.assertEqual(ast.dump(before),ast.dump(after))


if __name__=='__main__':unittest.main()
