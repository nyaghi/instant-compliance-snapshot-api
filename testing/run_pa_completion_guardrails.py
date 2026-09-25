"""PA's public controller clears rows before its HTTP search has completed."""
import sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

ORG = SimpleNamespace(organization_name='Completion Control Foundation', ein='12-3456789')

def result(status='Not Registered'):
    row = c.checker.StateResult(ORG.organization_name, ORG.ein, 'PA', status, 'https://www.charities.pa.gov/')
    row.success = True
    row.source_note = 'PA search results did not contain a matching EIN row.'
    return row

def search(**kw):
    return dict(step='search', ein='123456789', name='', complete=True,
                http_status=200, row_eins=[], **kw)

class CompletionControls(unittest.TestCase):
    def guard(self, observations, row=None):
        return c.pa_guard_search_completion(row or result(), ORG, observations)

    def test_blank_table_without_search_response_is_not_negative(self):
        self.assertEqual(self.guard([]).status, 'Unable to Verify')

    def test_pending_request_is_not_negative(self):
        row=search(); row['complete']=False
        self.assertEqual(self.guard([row]).status, 'Unable to Verify')

    def test_http_500_is_source_failure_not_negative(self):
        row=search(); row.update(http_status=500, complete=False)
        actual=self.guard([row])
        self.assertEqual(actual.status, 'Site Not Reachable')
        self.assertIn('HTTP 500',actual.source_note)
        self.assertEqual(actual.reason_code,'PA_INCOMPLETE_SEARCH')
        self.assertFalse(actual.success)

    def test_lookup_data_or_navigation_failure_is_not_negative(self):
        for step in ['lookup','page']:
            self.assertEqual(self.guard([dict(step=step,http_status=500)]).status,'Site Not Reachable')

    def test_transport_failure_is_not_negative(self):
        row=search(); row.update(complete=False,failure='Network failure')
        self.assertEqual(self.guard([row]).status,'Site Not Reachable')

    def test_completed_empty_ein_keeps_negative(self):
        self.assertEqual(self.guard([search()]).status,'Not Registered')

    def test_different_ein_cannot_establish_requested_negative(self):
        row=search();row['ein']='987654321'
        self.assertEqual(self.guard([row]).status,'Unable to Verify')

    def test_returned_ein_row_missing_from_dom_cannot_be_negative(self):
        row=search();row['row_eins']=['123456789']
        self.assertEqual(self.guard([row]).status,'Unable to Verify')

    def test_completed_name_search_preserves_existing_bounded_search_policy(self):
        row=result();row.queries_attempted=['Completion Control']
        alias=search();alias.update(ein='',name='Completion Control')
        self.assertEqual(self.guard([search(),alias],row).status,'Not Registered')

    def test_unsubmitted_or_uncompleted_name_query_cannot_be_negative(self):
        for failure in ['absent','pending']:
            row=result();row.queries_attempted=['Completion Control']
            observations=[search()]
            if failure=='pending':
                alias=search();alias.update(ein='',name='Completion Control',complete=False)
                observations.append(alias)
            self.assertEqual(self.guard(observations,row).status,'Unable to Verify')

    def test_confirmed_statuses_and_same_ein_matching_are_unchanged(self):
        for status in ['Current','Upcoming Filing','Delinquent','Exempt','Revoked','Closed / Withdrawn / Canceled']:
            row=result(status)
            self.assertIs(self.guard([],row),row)
            self.assertEqual(row.status,status)

    def test_retry_is_bounded_and_can_recover(self):
        failed=dict(status='Unable to Verify',success=False,reason_code='PA_INCOMPLETE_SEARCH')
        for second,expected in [(dict(status='Current',success=True),'Current'),(failed,'Unable to Verify')]:
            with patch.object(c,'run_state_lookup',side_effect=[dict(failed),dict(second)]) as lookup, \
                 patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_DELAY_SECONDS',0), \
                 patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS',2):
                actual=c.run_single_state_lookup_reliably(ORG.organization_name,ORG.ein,'PA')
            self.assertEqual(lookup.call_count,2)
            self.assertEqual(actual['status'],expected)

class Page:
    def __init__(self):self.listeners={};self.clock=0;self.pending=[]
    def on(self,event,fn):self.listeners[event]=fn
    def remove_listener(self,event,fn):self.listeners.pop(event)
    def wait_for_timeout(self,ms):
        self.clock+=ms/1000
        for when,fn in list(self.pending):
            if self.clock>=when:
                self.pending.remove((when,fn));fn()
    def emit(self,status=200,payload=None,ein='123456789',complete=True,name='',delay=0):
        req=SimpleNamespace(url='https://www.charities.pa.gov/api/Charities/Search',
                            resource_type='xhr',post_data_json={'EIN':ein,'EntityName':name})
        self.listeners['request'](req)
        if complete:
            def read():
                if isinstance(payload,Exception):raise payload
                return {'Table':[]} if payload is None else payload
            send=lambda:self.listeners['response'](SimpleNamespace(request=req,status=status,json=read))
            if delay:self.pending.append((self.clock+delay,send))
            else:send()

class EventControls(unittest.TestCase):
    def run_search(self,status=200,payload=None,complete=True):
        page=Page()
        def core(p,org,guard,wait,offset):
            p.emit(status,payload,complete=complete)
            return guard(result())
        with patch.object(c,'search_pa_with_name_fallback_core',side_effect=core):
            actual=c.search_pa_with_name_fallback(page,ORG)
        self.assertFalse(page.listeners)
        return actual

    def test_real_event_order_complete_empty_response(self):
        self.assertEqual(self.run_search().status,'Not Registered')

    def test_server_error_and_pending_event_order(self):
        self.assertEqual(self.run_search(500).status,'Site Not Reachable')
        self.assertEqual(self.run_search(complete=False).status,'Unable to Verify')

    def test_html_invalid_schema_and_broken_response_are_not_negative(self):
        for payload in ['<html>Server Error</html>',{}, {'Table':None}, {'Table':['bad row']}, ValueError('invalid JSON')]:
            self.assertEqual(self.run_search(payload=payload).status,'Unable to Verify')

    def test_ein_response_before_render_is_not_negative(self):
        self.assertEqual(self.run_search(payload={'Table':[{'EIN':'12-3456789'}]}).status,'Unable to Verify')

    def test_faulty_attempt_does_not_contaminate_next_request(self):
        self.assertEqual(self.run_search(500).status,'Site Not Reachable')
        self.assertEqual(self.run_search().status,'Not Registered')

    def test_base_incomplete_search_short_circuits_name_fallback(self):
        page=Page()
        def initial(p,org):p.emit(500);return result()
        with patch.object(c.checker,'search_pa',side_effect=initial), \
             patch.object(c,'build_search_queries') as names:
            actual=c.search_pa_with_name_fallback(page,ORG)
        names.assert_not_called()
        self.assertEqual(actual.status,'Site Not Reachable')

    def wait_case(self,setup,query='Completion Control',seconds=9):
        page=Page();out={}
        def core(p,org,guard,wait,offset):
            setup(p,offset,out)
            out['complete']=wait(query,out['offset'],p.clock+seconds)
            out['elapsed']=p.clock
            return result('Current')
        with patch.object(c,'search_pa_with_name_fallback_core',side_effect=core), \
             patch.object(c.time,'monotonic',side_effect=lambda:page.clock):
            actual=c.search_pa_with_name_fallback(page,ORG)
        self.assertFalse(page.listeners)
        return out,actual

    def test_slow_matching_response_is_awaited_before_return(self):
        def setup(p,offset,out):
            out['offset']=offset();p.emit(ein='',name='Completion Control',delay=6)
        out,actual=self.wait_case(setup)
        self.assertTrue(out['complete']);self.assertGreaterEqual(out['elapsed'],6)
        self.assertTrue(actual.source_attempts[0]['complete'])
        self.assertGreaterEqual(actual.source_attempts[0]['completed_seconds'],6)

    def test_old_same_query_response_cannot_complete_new_request(self):
        def setup(p,offset,out):
            p.emit(ein='',name='Completion Control')
            out['offset']=offset();p.emit(ein='',name='Completion Control',delay=5)
        out,_=self.wait_case(setup)
        self.assertTrue(out['complete']);self.assertGreaterEqual(out['elapsed'],5)

    def test_other_name_or_ein_response_cannot_complete_query(self):
        def setup(p,offset,out):
            out['offset']=offset();p.emit(name='Completion Control')
            p.emit(ein='',name='Different Name')
            p.emit(ein='',name='Completion Control',complete=False)
        out,_=self.wait_case(setup)
        self.assertFalse(out['complete']);self.assertAlmostEqual(out['elapsed'],9,places=2)

    def test_deadline_is_bounded_and_late_response_is_not_accepted(self):
        def setup(p,offset,out):
            out['offset']=offset();p.emit(ein='',name='Completion Control',delay=10)
        out,_=self.wait_case(setup)
        self.assertFalse(out['complete']);self.assertAlmostEqual(out['elapsed'],9,places=2)

    def test_error_response_ends_wait_without_claiming_completion(self):
        def setup(p,offset,out):
            out['offset']=offset();p.emit(status=503,ein='',name='Completion Control',delay=1)
        out,_=self.wait_case(setup)
        self.assertFalse(out['complete']);self.assertLess(out['elapsed'],2)

    def test_malformed_body_does_not_count_as_completed_response(self):
        def setup(p,offset,out):
            out['offset']=offset();p.emit(ein='',name='Completion Control',payload={'Table':None})
        out,_=self.wait_case(setup)
        self.assertFalse(out['complete']);self.assertAlmostEqual(out['elapsed'],9,places=2)

    def test_delayed_network_failure_ends_wait(self):
        def setup(p,offset,out):
            out['offset']=offset()
            req=SimpleNamespace(url='https://www.charities.pa.gov/api/Charities/Search',resource_type='xhr',
                                post_data_json={'EIN':'','EntityName':'Completion Control'})
            p.listeners['request'](req)
            p.pending.append((1,lambda:p.listeners['requestfailed'](req)))
        out,_=self.wait_case(setup)
        self.assertFalse(out['complete']);self.assertLess(out['elapsed'],2)

if __name__=='__main__':unittest.main(verbosity=2)
