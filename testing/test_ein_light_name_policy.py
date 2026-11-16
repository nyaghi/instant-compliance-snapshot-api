"""Completed EIN negatives plus one bounded optional name pass; no network."""
import json
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch, MagicMock
import registry_snapshot_server as c
from deployment.state_snapshots import DEADLINE

ROSTER = json.loads((Path(__file__).parent / 'fixtures/fresh-five/LOCAL-70.json').read_text())


class PennsylvaniaLightFallback(unittest.TestCase):
    def run_case(self, row, *, duration=10, initial='Not Registered', error=None, parent=200):
        org = c.checker.Organization(row['name'], row['ein'])
        clock, calls = [0.0], []
        empty = c.checker.StateResult(org.organization_name, org.ein, 'PA', initial, 'https://www.charities.pa.gov/')
        empty.success = initial == 'Not Registered'
        observations = [{'step': 'search', 'ein': org.ein, 'complete': True,
                         'http_status': 200, 'row_eins': []}]
        def guard(result):
            return c.pa_guard_search_completion(result, org, observations + getattr(result, '_pa_api_attempts', []))
        def fetch(url, deadline, **kw):
            calls.append((json.loads(kw['data'])['EntityName'], clock[0], deadline))
            if error == 'http':
                clock[0] = deadline
                raise urllib.error.HTTPError(url, 503, 'Unavailable', {}, None)
            if error == 'malformed':
                clock[0] += .1
                return b'{"Table":[],"Table1":[{"RESULTCOUNT":5}]}'
            if clock[0] + duration >= deadline:
                clock[0] = deadline
                raise TimeoutError('shared allowance')
            clock[0] += duration
            return b'{"Table":[],"Table1":[{"RESULTCOUNT":0}]}'
        token = DEADLINE.set(parent)
        try:
            with patch.object(c.time, 'monotonic', side_effect=lambda: clock[0]), \
                 patch.object(c.checker, 'search_pa', return_value=empty), \
                 patch.object(c, 'known_names_for_ein', return_value=row.get('aliases', [])), \
                 patch.object(c, 'identity_fetch', side_effect=fetch), \
                 patch.object(c, 'trial_identity', return_value={'origin': 'local'}):
                result = c.search_pa_with_name_fallback_core(None, org, guard)
                result = guard(result)
        finally:
            DEADLINE.reset(token)
        return result, calls, clock[0]

    def test_seventy_saved_organizations_share_one_twenty_second_limit(self):
        self.assertEqual(len(ROSTER), 70)
        for row in ROSTER:
            with self.subTest(name=row['name']):
                result, calls, elapsed = self.run_case(row, duration=10)
                self.assertEqual(result.status, 'Not Registered')
                self.assertTrue(result.success)
                self.assertLessEqual(elapsed, 20)
                self.assertTrue(all(stop == 20 for _, _, stop in calls))
                self.assertEqual(len(calls), len({name.casefold() for name, _, _ in calls}))

    def test_completed_ein_required_no_names_on_unavailable_ein(self):
        for status in ['Site Not Reachable', 'Current', 'Needs Review']:
            result, calls, _ = self.run_case(ROSTER[0], initial=status)
            self.assertEqual(result.status, status)
            self.assertEqual(calls, [])

    def test_real_http_error_at_deadline_is_still_unavailable(self):
        result, _, _ = self.run_case(ROSTER[0], error='http')
        self.assertEqual(result.status, 'Site Not Reachable')

    def test_truncated_response_is_not_a_clean_negative(self):
        result, _, _ = self.run_case(ROSTER[0], error='malformed')
        self.assertNotEqual(result.status, 'Not Registered')

    def test_parent_deadline_cannot_expand(self):
        result, calls, elapsed = self.run_case(ROSTER[0], parent=9)
        self.assertLessEqual(elapsed, 8)
        self.assertTrue(all(stop <= 8 for _, _, stop in calls))

    def test_stale_or_absent_identity_cannot_authorize_cutoff(self):
        org = c.checker.Organization('Example', '123456789')
        for identity in [None, ('Other', '123456789'), ('Example', '999999999')]:
            result = c.checker.StateResult(org.organization_name, org.ein, 'PA', 'Not Registered', 'https://www.charities.pa.gov/')
            result._cc_pa_light_name_identity = identity
            observations = [{'step': 'search', 'ein': org.ein, 'complete': True, 'row_eins': []},
                            {'step': 'search', 'ein': '', 'complete': False, 'failure': 'limit', 'failure_kind': 'budget'}]
            self.assertNotEqual(c.pa_guard_search_completion(result, org, observations).status, 'Not Registered')

class OtherEinFallbacks(unittest.TestCase):
    def result(self, org, state, status='Not Registered'):
        value = c.checker.StateResult(org.organization_name, org.ein, state, status, 'https://state.example/')
        value.success = True
        return value

    def test_colorado_seventy_plans_bound_only_after_empty_ein(self):
        from deployment.co_budget import STOP
        for row in ROSTER:
            with self.subTest(name=row['name']):
                org=c.checker.Organization(row['name'],row['ein']);clock=[0.0];calls=[]
                def search(page, query):
                    calls.append((query.ein,clock[0],STOP.get()))
                    if query.ein:return self.result(org,'CO')
                    if clock[0]+11>=STOP.get():clock[0]=STOP.get();raise TimeoutError('bounded')
                    clock[0]+=11
                    return self.result(org,'CO')
                with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.checker,'search_co',side_effect=search),patch.object(c,'known_names_for_ein',return_value=row.get('aliases',[])):
                    result=c.search_co_with_name_fallback(None,org)
                self.assertEqual(calls[0][0],org.ein)
                self.assertTrue(all(not ein and stop==20 for ein,_,stop in calls[1:]))
                self.assertLessEqual(clock[0],20);self.assertEqual(result.status,'Not Registered')

    def test_new_jersey_seventy_plans_share_deadline_without_repeating_ein(self):
        for row in ROSTER:
            with self.subTest(name=row['name']):
                org=c.checker.Organization(row['name'],row['ein']);clock=[0.0];calls=[]
                def search(page, query, original, deadline):
                    calls.append((query.organization_name,deadline))
                    if clock[0]+11>=deadline:clock[0]=deadline;raise TimeoutError('bounded')
                    clock[0]+=11
                    return self.result(org,'NJ')
                with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'nj_same_lookup_zero_queries',return_value=[]),patch.object(c,'search_nj_direct',return_value=self.result(org,'NJ')) as primary,patch.object(c,'nj_bounded_name_query',side_effect=search),patch.object(c,'known_names_for_ein',return_value=row.get('aliases',[])),patch.object(c,'trial_identity',return_value={'origin':'local'}):
                    result=c.search_nj_with_name_fallback(None,org)
                self.assertEqual(primary.call_count,1);self.assertEqual(primary.call_args.args[1].ein,org.ein)
                self.assertLessEqual(clock[0],20);self.assertTrue(all(stop==20 for _,stop in calls))
                self.assertEqual(result.status,'Not Registered')

    def test_michigan_optional_pass_stops_at_shared_limit_with_ein_proof(self):
        org=c.checker.Organization('Example Relief','123456789');clock=[0.0]
        for has_proof in [True,False]:
            clock[0]=0;page=MagicMock();page._cc_mi_lookup_deadline=100
            page._cc_mi_search_progress={'identity':(org.organization_name,org.ein),'completed_ein_identity':(org.organization_name,org.ein)if has_proof else None,'browser_ein_confirmed_empty':True}
            def navigate(*args,**kwargs):clock[0]=20;raise TimeoutError('bounded')
            page.goto.side_effect=navigate
            with patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(c,'state_extension_module',return_value=MagicMock()),patch.object(c,'patch_mi_module_for_fast_lookups'),patch.object(c,'known_names_for_ein',return_value=[]),patch.object(c,'mi_name_fallback_queries',return_value=['Example Relief']):
                result=c.search_mi_name_fallback(page,org)
            self.assertEqual(c.public_status(result),'Not Registered'if has_proof else'Site Not Reachable')

    def test_positive_ein_never_enters_optional_fallback(self):
        org=c.checker.Organization('Example Relief','123456789')
        for state,function,primary in [('CO',c.search_co_with_name_fallback,c.checker),('NJ',c.search_nj_with_name_fallback,c)]:
            target='search_co'if state=='CO'else'search_nj_direct'
            with patch.object(primary,target,return_value=self.result(org,state,'Current')),patch.object(c,'nj_same_lookup_zero_queries',return_value=[]),patch.object(c,'co_light_name_fallback')as co,patch.object(c,'nj_bounded_name_query')as nj:
                self.assertEqual(function(None,org).status,'Current');co.assert_not_called();nj.assert_not_called()

    def test_california_seventy_empty_ein_fallbacks_share_one_deadline(self):
        for row in ROSTER:
            org=c.checker.Organization(row['name'],row['ein']);clock=[0.0];calls=[]
            def names(query, *, deadline):
                calls.append((query,deadline));clock[0]=deadline;raise TimeoutError('bounded')
            with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.checker,'search_ca',return_value=self.result(org,'CA',c.checker.STATUS_NOT_REGISTERED)),patch.object(c.checker,'ca_evoke_entity_search_by_name',side_effect=names),patch.object(c,'known_names_for_ein',return_value=row.get('aliases',[])),patch.object(c,'trial_identity',return_value=None):
                result=c.search_ca_master(None,org)
            self.assertEqual(c.public_status(result),'Not Registered');self.assertEqual(clock[0],20);self.assertEqual(calls[0][1],20)

    def test_massachusetts_reload_and_name_form_share_twenty_seconds(self):
        org=c.checker.Organization('Example Relief','123456789');page=MagicMock();clock=[0.0]
        def reload(**kw):clock[0]+=8
        def select(**kw):
            if kw['label']=='Charity Name Contains':
                self.assertEqual(kw['timeout'],12000);clock[0]+=kw['timeout']/1000;raise TimeoutError('bounded')
        page.reload.side_effect=reload;page.get_by_role.return_value.first.select_option.side_effect=select
        with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'registry_page_body',return_value='No Charity Found'):
            result,_=c.search_ma_master(page,org,None)
        self.assertEqual(c.public_status(result),'Not Registered');self.assertEqual(clock[0],20)

    def test_hawaii_name_phase_does_not_get_the_ein_allowance(self):
        org=c.checker.Organization('Example Relief','123456789');clock=[0.0];calls=[]
        def search(page,name,ein,deadline):
            calls.append((name,ein,deadline))
            if not name:return []
            self.assertEqual(deadline,20);clock[0]=deadline;raise TimeoutError('bounded')
        with patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(c.time,'sleep'),patch.object(c,'hi_submit_completed_search',side_effect=search),patch.object(c.checker,'find_visible_input',return_value=MagicMock()),patch.object(c.checker,'safe_wait_for_network_idle'),patch.object(c,'build_search_queries',return_value=['Example Relief']):
            result=c.search_hi_precise(MagicMock(),org)
        self.assertTrue(all(not name for name,_,_ in calls[:2]));self.assertEqual(c.public_status(result),'Not Registered');self.assertEqual(clock[0],20)

    def test_minnesota_name_navigation_cannot_extend_allowance(self):
        org=c.checker.Organization('Example Relief','123456789');page=MagicMock();clock=[0.0];calls=[]
        def navigate(*args,**kw):
            calls.append(kw['timeout'])
            if len(calls)==3:
                self.assertEqual(kw['timeout'],20000);clock[0]+=20;raise TimeoutError('bounded')
        page.goto.side_effect=navigate
        with patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(c.time,'sleep'),patch.object(c,'readable_page_text',return_value='No matching records found'),patch.object(c.checker,'find_visible_input',return_value=MagicMock()),patch.object(c.checker,'safe_wait_for_network_idle'),patch.object(c,'known_names_for_ein',return_value=[]),patch.object(c,'build_search_queries',return_value=['Example Relief']):
            result=c.search_mn(page,org)
        self.assertEqual(c.public_status(result),'Not Registered');self.assertEqual(clock[0],20);self.assertTrue(result.success)

class WashingtonLightFallback(unittest.TestCase):
    def test_seventy_pending_sources_stop_without_resetting_deadline(self):
        module=c.load_wa_nm_module()
        for row in ROSTER:
            org=c.checker.Organization(row['name'],row['ein']);page=MagicMock();clock=[0.0]
            def wait(seconds):clock[0]+=seconds
            with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.time,'sleep',side_effect=wait),patch.object(module,'switch_to_name_mode'),patch.object(c,'wa_fill_ready_name_and_search',return_value=True),patch.object(module,'wa_search_tracker_state',return_value={'completed':1,'pending':1}):
                result=c.wa_light_name_fallback(page,org)
            self.assertEqual(result,'NO_VALUE');self.assertLessEqual(clock[0],20)

    def test_new_completed_response_required_and_positive_detail_retained(self):
        module=c.load_wa_nm_module();org=c.checker.Organization('Example Relief','123456789');page=MagicMock();clock=[0.0]
        old={'completed':1,'pending':0,'lastStatus':200,'lastText':'[]'}
        row={'EntityName':org.organization_name,'FEINNumber':org.ein,'Criteria':{'TotalRowCount':1},'TotalPageCount':1}
        new={**old,'completed':2,'lastText':json.dumps([row])}
        page.locator.return_value.filter.return_value.count.return_value=1
        def wait(seconds):clock[0]+=seconds
        with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.time,'sleep',side_effect=wait),patch.object(module,'switch_to_name_mode'),patch.object(c,'wa_fill_ready_name_and_search',return_value=True),patch.object(module,'wa_search_tracker_state',side_effect=[old,old,new]):
            result=c.wa_light_name_fallback(page,org)
        self.assertIs(result,page.locator.return_value.filter.return_value);self.assertGreater(clock[0],0)

    def test_http_failure_and_malformed_positive_never_become_negative(self):
        module=c.load_wa_nm_module();org=c.checker.Organization('Example Relief','123456789')
        for tracker in [{'failed':1,'lastStatus':503},{'completed':2,'pending':0,'lastStatus':200,'lastText':'[{"EntityName":"Example Relief"}]'}]:
            with patch.object(module,'switch_to_name_mode'),patch.object(c,'wa_fill_ready_name_and_search',return_value=True),patch.object(module,'wa_search_tracker_state',side_effect=[{'completed':1},tracker]):
                self.assertIsNone(c.wa_light_name_fallback(MagicMock(),org))

if __name__ == '__main__':
    unittest.main(verbosity=2)
