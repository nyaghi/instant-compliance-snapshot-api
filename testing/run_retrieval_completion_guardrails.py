"""A completed empty record is evidence; failed retrieval is not."""
import io
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class CompletionControls(unittest.TestCase):
    def setUp(self):
        self.org = c.checker.Organization('Example Charity', '12-3456789')
        self.row = dict(name='Example Charity', number='CO123', status='ACTIVE',
                        href='ShowDetail.aspx?detail=123', location='Chicago, IL')

    def maine(self, body=None, failure=False):
        opener = Mock()
        if failure:
            opener.open.side_effect = TimeoutError('detail did not load')
        else:
            opener.open.side_effect = lambda *a, **k: io.BytesIO(body.encode())
        return c.me_result_from_search(self.org, self.row, opener, True, '')

    def test_maine_timed_out_active_detail_cannot_be_current(self):
        result = self.maine(failure=True)
        self.assertIn(c.public_status(result), {'Unable to Verify', 'Site Not Reachable'})
        self.assertFalse(result.success)
        self.assertEqual(result.reason_code, 'ME_DETAIL_INCOMPLETE')
        c.enrich_me_result_from_body(result, result._cc_detail_body)
        self.assertFalse(result.success)
        self.assertNotIn(c.true_status_from_body(result, result._cc_detail_body), {'Current', 'Not Registered'})

    def test_maine_active_date_drives_upcoming_not_generic_current(self):
        result = self.maine('License Number: CO123 Status: Active Expiration Date: 11/30/2026')
        self.assertTrue(result.success)
        self.assertIn('11/30/2026', result.raw_status_text)

    def test_maine_retries_failed_detail_without_repeating_search(self):
        opener = Mock()
        opener.open.side_effect = [TimeoutError('slow'), io.BytesIO(b'License Number: CO123 Status: Active Expiration Date: 11/30/2026')]
        result = c.me_result_from_search(self.org, self.row, opener, True, '')
        self.assertTrue(result.success)
        self.assertEqual(opener.open.call_count, 2)
        self.assertIn('11/30/2026', result.raw_status_text)

    def test_maine_recovery_does_not_repeat_completed_empty_aliases(self):
        progress = {'completed': {'Example Charity'}, 'deadline': time.perf_counter()+200}
        self.org._cc_me_progress = progress
        session = Mock();session.search.return_value = ([], session)
        with patch.object(c, 'MaineRegistrySession', return_value=session), \
             patch.object(c, 'me_fast_direct_query_variants', return_value=['Example Charity', 'Former Charity']):
            result = c.me_fast_direct_confirmation_result(self.org)
        self.assertEqual(c.public_status(result), 'Not Registered')
        session.search.assert_called_once_with('Former Charity')

    def test_maine_recovery_reuses_selected_credential_after_detail_failure(self):
        self.org._cc_me_progress = {'completed': {'Example Charity'}, 'best_row': self.row}
        session = Mock();session.open.return_value = io.BytesIO(b'License Number: CO123 Status: Active Expiration Date: 11/30/2026')
        with patch.object(c, 'MaineRegistrySession', return_value=session), \
             patch.object(c, 'me_fast_direct_query_variants', return_value=['Example Charity']):
            result = c.me_fast_direct_confirmation_result(self.org)
        self.assertTrue(result.success)
        session.search.assert_not_called()

    def test_maine_pending_credential_is_not_historical_failed_credential(self):
        self.row.update(number='CO456', status='Pending')
        result = self.maine('License Number: CO123 Status: Failed to Renew Expiration Date: 11/30/2019 '
                            'Pending Number: CO456 Status: Pending Application Date: 9/1/2026')
        self.assertEqual(result.matched_registry_identifier, 'CO456')
        self.assertEqual(c.public_status(result), 'Pending')
        self.assertNotIn('11/30/2019', result.raw_status_text)

    def test_maine_explicit_pending_row_survives_unavailable_optional_date(self):
        self.row.update(status='Pending')
        result = self.maine(failure=True)
        self.assertEqual(c.public_status(result), 'Pending')

    def test_maine_completed_empty_search_stays_negative(self):
        result = c.me_result_from_search(self.org, None, None, True, '')
        self.assertEqual(c.public_status(result), 'Not Registered')

    def test_maine_incomplete_search_is_not_negative(self):
        self.assertIsNone(c.me_result_from_search(self.org, None, None, True, 'timeout'))

    def test_maine_wrong_credential_still_rejected(self):
        with self.assertRaises(ValueError):
            self.maine('License Number: CO999 Status: Failed to Renew Expiration Date: 11/30/2019')

    def test_wisconsin_separator_equivalent_precedes_short_probes(self):
        org = c.checker.Organization('Make-A-Wish Foundation of America', '86-0481941')
        with patch.object(c, 'known_names_for_ein', return_value=['Make-A-Wish', 'MAWF']):
            names = c.wi_search_names_for_org(org)
        self.assertIn('Make A Wish Foundation of America', names[:3])
        self.assertEqual(names[0], org.organization_name)

    def test_separator_query_does_not_relax_branch_identity(self):
        with patch.object(c, 'known_names_for_ein', return_value=[]):
            self.assertFalse(c.registry_name_is_safe_for_org(
                'Beth Israel Deaconess Hospital - Plymouth',
                'Beth Israel Deaconess Hospital - Milton', '04-2103604'))

    def test_hawaii_only_completed_success_payload_is_search_evidence(self):
        for payload in ({}, {'status': 'FAILURE'}, {'status': 'SUCCESS'},
                        {'status': 'SUCCESS', 'payload': {'results': None}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                c.hi_completed_search_rows(payload)
        self.assertEqual(c.hi_completed_search_rows({'status': 'SUCCESS', 'payload': {'results': []}}), [])

    def test_hawaii_explicit_no_registration_response_is_a_completed_negative(self):
        data={'status':'FAILURE','message':'The charitable organization you entered is not registered in our system. You cannot continue unless you add a registered charitable organization.'}
        self.assertEqual(c.hi_completed_search_rows(data),[])
        with self.assertRaises(ValueError):
            c.hi_completed_search_rows({'status':'FAILURE','message':'The search service is unavailable.'})

    def test_hawaii_incomplete_result_row_is_not_an_empty_search(self):
        with self.assertRaises(ValueError):
            c.hi_completed_search_rows({'status': 'SUCCESS', 'payload': {'results': [{}]}})
        row = {'fein': '12-3456789', 'organizationName': 'Example Charity'}
        self.assertEqual(c.hi_completed_search_rows({'status': 'SUCCESS', 'payload': {'results': [row]}}), [row])

    def test_ma_completed_empty_history_retains_approved_delinquent_rule(self):
        page = Mock()
        page.locator.return_value.inner_text.return_value = 'AG Account Number 012345'
        completed = {'record': {'ago_account': '012345', 'registry_status': 'Not Doing Business in Mass'},
                     'filings': {'012345': {'empty': True}}}
        result = c.checker.StateResult(self.org.organization_name, self.org.ein, 'MA', 'Current', '')
        evidence = c.ma_read_latest_form_pc(page, result, 'AG Account Number 012345', completed)
        result = c.annotate_ma_visible_form_pc_due(result, evidence)
        self.assertEqual(result.status, 'Delinquent')
        page.context.request.get.assert_not_called()

    def test_ma_unloaded_history_cannot_be_called_completed_empty(self):
        page = Mock()
        page.locator.return_value.inner_text.return_value = 'AG Account Number 012345'
        page.get_by_role.return_value.all_inner_texts.return_value = []
        completed = {'record': {'ago_account': '012345', 'registry_status': 'Registered'}}
        evidence = c.ma_read_latest_form_pc(page, Mock(), 'AG Account Number 012345', completed)
        self.assertFalse(evidence.get('empty_history_confirmed'))

    def test_ma_failed_popup_is_retrievable_not_an_empty_history(self):
        page = Mock()
        page.get_by_role.return_value.all_inner_texts.return_value = ['2024 Form-PC Data']
        page.expect_popup.side_effect = TimeoutError('popup never loaded')
        evidence = c.ma_read_latest_form_pc(page, Mock(), 'AG Account Number 012345')
        self.assertTrue(evidence['detail_read_incomplete'])
        self.assertFalse(evidence.get('empty_history_confirmed'))

    def test_state_http_budgets_are_independent(self):
        budgets = {'ME': 285, 'WV': 140, 'OK': 115, 'AK': 115,
                   'MI': 2*c.MI_LOOKUP_MAX_SECONDS+30, 'CA': c.BATCH_FANOUT_STATE_TIMEOUT_SECONDS,
                   'FL': c.BATCH_FANOUT_STATE_TIMEOUT_SECONDS, 'MA': c.BATCH_FANOUT_STATE_TIMEOUT_SECONDS}
        for state, expected in budgets.items():
            response = Mock()
            response.__enter__ = Mock(return_value=response);response.__exit__=Mock(return_value=False)
            response.read.return_value = json.dumps({'results':[{'state':state,'status':'Current','success':True}]}).encode()
            with self.subTest(state=state), patch.object(c,'BATCH_FANOUT_API_URLS',['https://qa.invalid/api/check']), \
                 patch.object(c.urllib.request,'urlopen',return_value=response) as request:
                result = c.run_fanout_state_lookup_for_batch('Example Charity','12-3456789',state)
                self.assertEqual(request.call_args.kwargs['timeout'],expected)
                self.assertEqual(result['status'],'Current')

    def test_maine_queue_wait_does_not_spend_search_allowance(self):
        now=[0.0]
        lock=Mock();lock.acquire.side_effect=lambda **k: (now.__setitem__(0,50.0) or True)
        self.org._cc_me_progress={'deadline':265.0}
        done=c.checker.StateResult('Example Charity','12-3456789','ME','Not Registered','',success=True)
        with patch.object(c.time,'perf_counter',side_effect=lambda:now[0]), \
             patch.object(c,'ME_LOOKUP_LOCK',lock),patch.object(c,'ME_LAST_LOOKUP_FINISHED',-10), \
             patch.object(c,'me_fast_direct_confirmation_result',return_value=done) as search:
            c.search_me_serialized(Mock(),self.org)
        self.assertEqual(search.call_args.kwargs['deadline'],155.0)
        lock.release.assert_called_once()

    def test_waiting_maine_does_not_acquire_any_browser(self):
        lock=Mock();lock.acquire.return_value=False
        with patch.object(c,'ME_LOOKUP_LOCK',lock),patch.object(c,'run_state_lookup') as lookup:
            result=c.run_me_lookup_with_lane('Example Charity','12-3456789',{'deadline':time.perf_counter()+200})
        lookup.assert_not_called();lock.release.assert_not_called()
        self.assertEqual(result['reason_code'],'ME_QUEUE_TIMEOUT')

    def test_maine_exception_releases_lane_for_next_organization(self):
        lock=Mock();lock.acquire.return_value=True;progress={'deadline':time.perf_counter()+200}
        with patch.object(c,'ME_LOOKUP_LOCK',lock),patch.object(c,'run_state_lookup',side_effect=ValueError('injected')):
            with self.assertRaises(ValueError):c.run_me_lookup_with_lane('Example Charity','12-3456789',progress)
        lock.release.assert_called_once();self.assertNotIn('lane_owned',progress)

    def test_maine_releases_registry_lane_before_browser_cleanup(self):
        lock=Mock();lock.acquire.return_value=True;progress={'deadline':time.perf_counter()+200}
        done=c.checker.StateResult('Example Charity','12-3456789','ME','Not Registered','',success=True)
        def lookup(name,ein,state,**kwargs):
            self.org._cc_me_progress=kwargs['me_progress']
            c.search_me_serialized(Mock(),self.org)
            lock.release.assert_called_once()  # Browser cleanup follows this point.
            return {'status':'Not Registered'}
        with patch.object(c,'ME_LOOKUP_LOCK',lock),patch.object(c,'ME_LAST_LOOKUP_FINISHED',-10), \
             patch.object(c,'run_state_lookup',side_effect=lookup),patch.object(c,'me_fast_direct_confirmation_result',return_value=done):
            c.run_me_lookup_with_lane('Example Charity','12-3456789',progress)
        lock.acquire.assert_called_once();lock.release.assert_called_once()

    def wv_page(self, *, detail_failure=False, count_failure=False):
        page=Mock(); opened=[]
        cells=[Mock() for _ in range(5)]
        for cell,value in zip(cells,['123','Example Charity','Chicago','Charity','Active']):
            cell.inner_text.return_value=value
        cell_list=Mock();cell_list.count.return_value=5;cell_list.nth.side_effect=cells.__getitem__
        link=Mock()
        def click(**kwargs):
            if detail_failure and not opened:
                opened.append(False)
                raise TimeoutError('detail navigation timed out')
            opened.append(True)
        link.first.click.side_effect=click
        row=Mock();row.locator.side_effect=lambda selector:cell_list if selector=='td' else link
        rows=Mock();rows.count.return_value=1;rows.nth.return_value=row
        if count_failure:rows.count.side_effect=TimeoutError('table not readable')
        page.locator.side_effect=lambda selector:rows if selector=='tr' else Mock()
        def body(_):
            if opened and opened[-1]:
                return 'Organization Name\nExample Charity\nExpiration Date\n09/18/2027\nContact Name\nControl\nStatus\nActive\nStreet Address\nChicago'
            return 'Search results'
        return page,opened,body

    def test_wv_detail_retry_does_not_skip_the_found_candidate(self):
        self.org._cc_wv_progress={'completed':[], 'deadline':time.perf_counter()+115}
        page,opened,body=self.wv_page(detail_failure=True)
        with patch.object(c,'wv_preferred_query_variants',return_value=['Example Charity']), \
             patch.object(c,'registry_page_body',side_effect=body),patch.object(c,'safe_wait_for_network_idle'):
            first=c.search_wv_precise(page,self.org)
            second=c.search_wv_precise(page,self.org)
        self.assertFalse(first.success)
        self.assertEqual(c.public_status(second),'Current')
        self.assertEqual(second.matched_registry_identifier,'123')
        self.assertEqual(opened,[False,True])

    def test_wv_unreadable_table_does_not_complete_a_negative_query(self):
        self.org._cc_wv_progress={'completed':[], 'deadline':time.perf_counter()+115}
        page,_,body=self.wv_page(count_failure=True)
        with patch.object(c,'wv_preferred_query_variants',return_value=['Example Charity']), \
             patch.object(c,'registry_page_body',side_effect=body),patch.object(c,'safe_wait_for_network_idle'):
            result=c.search_wv_precise(page,self.org)
        self.assertFalse(result.success)
        self.assertNotEqual(c.public_status(result),'Not Registered')
        self.assertEqual(self.org._cc_wv_progress['completed'],[])

    def test_wv_unloaded_detail_cannot_reuse_search_row_active_status(self):
        self.org._cc_wv_progress={'completed':[], 'deadline':time.perf_counter()+115}
        page,opened,body=self.wv_page()
        with patch.object(c,'wv_preferred_query_variants',return_value=['Example Charity']), \
             patch.object(c,'registry_page_body',side_effect=lambda p:'Loading...' if opened else body(p)), \
             patch.object(c,'safe_wait_for_network_idle'):
            result=c.search_wv_precise(page,self.org)
        self.assertFalse(result.success)
        self.assertNotIn(c.public_status(result),{'Current','Not Registered'})
        self.assertEqual(self.org._cc_wv_progress['completed'],[])

    def test_wv_blank_result_page_is_not_an_empty_completed_search(self):
        self.org._cc_wv_progress={'completed':[], 'deadline':time.perf_counter()+115}
        page,_,body=self.wv_page()
        page.locator('tr').count.return_value=0
        with patch.object(c,'wv_preferred_query_variants',return_value=['Example Charity']), \
             patch.object(c,'registry_page_body',return_value='Searching...'),patch.object(c,'safe_wait_for_network_idle'):
            result=c.search_wv_precise(page,self.org)
        self.assertFalse(result.success)
        self.assertEqual(self.org._cc_wv_progress['completed'],[])

    def test_wisconsin_outer_retry_retains_completed_query_progress(self):
        seen=[]
        def lookup(name,ein,state,**kwargs):
            progress=kwargs.get('wi_progress')
            self.assertIsNotNone(progress)
            seen.append(progress)
            if len(seen)==1:
                progress['completed'].add('Example Charity')
                return {'state':'WI','status':'Site Not Reachable','success':False}
            self.assertIn('Example Charity',progress['completed'])
            return {'state':'WI','status':'Not Registered','success':True}
        with patch.object(c,'run_state_lookup',side_effect=lookup),patch.object(c.time,'sleep'):
            result=c.run_single_state_lookup_reliably('Example Charity','12-3456789','WI')
        self.assertEqual(result['status'],'Not Registered')
        self.assertIs(seen[0],seen[1])

    def test_wisconsin_parser_failure_does_not_complete_a_query(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=b'complete search table'
        opener=Mock();opener.open.return_value=response
        progress={'attempted':[],'completed':set()}
        with patch.object(c.urllib.request,'build_opener',return_value=opener), \
             patch.object(c,'wi_result_html_requires_verification',return_value=False), \
             patch.object(c,'wi_has_complete_results',return_value=True), \
             patch.object(c,'wi_best_match_from_html',side_effect=TimeoutError('result parsing incomplete')):
            with self.assertRaises(TimeoutError):
                c.wi_http_search_best_match(['Example Charity'],['Example Charity'],original_name='Example Charity',ein='12-3456789',progress=progress)
        self.assertEqual(progress['completed'],set())

    def test_wisconsin_browser_recovery_receives_same_completed_queries(self):
        progress={'attempted':['Example Charity'],'completed':{'Example Charity'}}
        runtime=Mock();runtime.__enter__=Mock(return_value=runtime);runtime.__exit__=Mock(return_value=False)
        lock=Mock();lock.acquire.return_value=True
        with patch.object(c.checker,'sync_playwright',return_value=runtime), \
             patch.object(c,'WI_BACKEND_BROWSER_SEMAPHORE',lock),patch.object(c,'configure_browser_context'), \
             patch.object(c,'search_wi',return_value=Mock()) as search:
            c.search_wi_backend_browser_fallback(self.org,max_seconds=20,progress=progress)
        self.assertIs(search.call_args.kwargs['progress'],progress)
        lock.release.assert_called_once()

    def test_wisconsin_incomplete_detail_recovers_only_same_credential(self):
        from datetime import date
        candidate={'score':5,'license_number':'123-800','registry_name':'Example Charity',
            'detail_href':'CredSummaryDetails.aspx?chid=123','location':'Chicago, IL',
            'expiration_date':date(2024,7,31),'identity_conflict':True,'identity_detail_unavailable':True}
        for number,name,status,expected in [('123-800','Example Charity','Revoked','Revoked'),
                ('999-800','Example Charity','Active','Unable to Confirm'),
                ('123-800','Different Charity','Active','Unable to Confirm')]:
            detail=f'Name : {name} Credential Type : Charitable Organization Credential Number : {number} Location : Chicago, IL Status License is not current ({status})'
            with self.subTest(number=number,name=name),patch.object(c,'wi_http_search_best_match',return_value=(candidate,True)), \
                    patch.object(c,'wi_reader_text',return_value=detail) as read, \
                    patch.object(c,'registry_address_evidence',return_value={'decision':'corroborated'}), \
                    patch.object(c,'public_profile_for_ein',return_value={}):
                result=c.search_wi(None,self.org,max_seconds=20)
            self.assertEqual(c.public_status(result),expected)
            read.assert_called_once()
            self.assertLessEqual(read.call_args.kwargs['deadline']-time.perf_counter(),12)

    def test_wisconsin_actual_name_conflict_does_not_trigger_missing_detail_retry(self):
        candidate={'score':5,'license_number':'123-800','registry_name':'Example Charity',
            'detail_href':'CredSummaryDetails.aspx?chid=123','identity_conflict':True}
        with patch.object(c,'wi_http_search_best_match',return_value=(candidate,True)),patch.object(c,'wi_reader_text') as read:
            result=c.search_wi(None,self.org,max_seconds=20)
        self.assertEqual(c.public_status(result),'Unable to Confirm');read.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
