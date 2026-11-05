"""Preserve bounded stop while allowing a responsive official search entrance."""
import unittest
import urllib.error
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock, patch
from deployment import or_reachability as m

DETAIL=m.SOURCE+'/Charity/details?charityID=202'

class Clock:
    value=0.
    def __call__(self):return self.value

class Response:
    status=200
    def __init__(self,url):self.url=url
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):raise AssertionError('Probe must never wait for a body')

class ReachabilityTests(unittest.TestCase):
    def invoke(self,events,url=DETAIL,deadline=float('inf')):
        clock=Clock();calls=[]
        def opener(req,timeout):
            calls.append((req.full_url,timeout));event=events[len(calls)-1]
            if event=='timeout':clock.value+=timeout;raise TimeoutError()
            if isinstance(event,int):raise urllib.error.HTTPError(req.full_url,event,'test',{},None)
            if event=='late':clock.value+=timeout+40
            else:clock.value+=1
            return Response('https://example.com/' if event=='redirect' else req.full_url)
        value=m.check(url,deadline=deadline,opener=opener,clock=clock)
        return value,calls

    def test_healthy_detail_is_one_request(self):
        result,calls=self.invoke(['ok']);self.assertTrue(result[0]);self.assertEqual(calls,[(DETAIL,8.)])
        self.assertEqual(result[2][0]['target'],'detail')

    def test_detail_timeout_search_success_allows_normal_collector(self):
        result,calls=self.invoke(['timeout','ok']);self.assertTrue(result[0])
        self.assertEqual(calls,[(DETAIL,8.),(m.SOURCE,16.)]);self.assertEqual(result[3],9.)
        self.assertEqual([x['target'] for x in result[2]],['detail','search'])

    def test_all_unavailable_stays_bounded_32_seconds(self):
        result,calls=self.invoke(['timeout']*3);self.assertFalse(result[0]);self.assertEqual(result[3],32.)
        self.assertEqual(calls,[(DETAIL,8.),(m.SOURCE,16.),(m.SOURCE,8.)])

    def test_source_root_stays_root(self):
        result,calls=self.invoke(['timeout','ok'],m.SOURCE);self.assertTrue(result[0])
        self.assertEqual([x[0] for x in calls],[m.SOURCE,m.SOURCE])

    def test_remaining_task_budget_is_not_extended(self):
        result,calls=self.invoke(['timeout']*3,deadline=12);self.assertFalse(result[0]);self.assertEqual(result[3],11.)
        self.assertEqual([x[1] for x in calls],[8.,3.])

    def test_no_budget_means_no_calls(self):
        result,calls=self.invoke([],deadline=1);self.assertFalse(result[0]);self.assertEqual(calls,[])

    def test_access_denial_remains_terminal(self):
        for code in (401,403,404):
            with self.subTest(code=code):
                result,calls=self.invoke([code]);self.assertEqual(result[1],'OR_SOURCE_ACCESS_REFUSED');self.assertEqual(len(calls),1)

    def test_transient_http_failure_can_recover(self):
        for code in (408,429,500,502,503,504):
            with self.subTest(code=code):
                result,calls=self.invoke([code,'ok']);self.assertTrue(result[0]);self.assertEqual(calls[1][0],m.SOURCE)

    def test_foreign_redirect_rejected(self):
        result,calls=self.invoke(['redirect']);self.assertEqual(result[1],'OR_SOURCE_ACCESS_REFUSED')
        self.assertEqual(len(calls),1)

    def test_late_success_rejected(self):
        result,calls=self.invoke(['late']);self.assertFalse(result[0]);self.assertEqual(result[2][0]['error_type'],'LateResponse')

    def test_unavailable_never_becomes_negative_registration(self):
        r=m.unavailable_result({'ein':'131930701','organization_name':'Test'},'29.2NY','OR_SOURCE_UNREACHABLE',[],32)
        self.assertFalse(r['success']);self.assertEqual(r['status'],'Site Not Reachable');self.assertEqual(r['evidence_url'],'')

    def test_other_state_limits_and_oregon_hard_stop_unchanged(self):
        self.assertEqual(m.task_allowance({'state':'OR','run_seconds':180}),75.)
        self.assertEqual(m.task_allowance({'state':'CA','run_seconds':180}),180)

    def test_real_queue_continues_only_after_probe_recovery(self):
        from deployment import queue_engine as engine
        for recovered in (True,False):
            with self.subTest(recovered=recovered):
                clock=Clock();calls=[];real_check=m.check
                def opener(req,timeout):
                    calls.append(req.full_url)
                    if len(calls)==1 or not recovered:
                        clock.value+=timeout;raise TimeoutError()
                    return Response(req.full_url)
                def probe(url,**kwargs):return real_check(url,opener=opener,clock=clock,**kwargs)
                collector=Mock(return_value=[{'state':'OR','status':'Unable to Confirm','success':False,'evidence_url':''}])
                master=SimpleNamespace(APP_VERSION='29.2NY',SUPPORTED_STATES={'OR'},
                    normalize_organization_requests=lambda *a,**k:[object()],
                    or_snapshot_row_for_ein=lambda ein:['202'],run_state_lookups_parallel=collector)
                job={'state':'OR','version':'29.2NY','_deadline_monotonic':75.,
                     'payload':{'organization_name':'Test','ein':'131930701','mode':'standard'}}
                with patch.object(m,'check',probe),patch.object(engine,'observe_fl_headers',return_value=nullcontext()),\
                     patch.object(engine,'observe_transport',return_value=nullcontext()),\
                     patch.object(engine,'observe_browser_transport',return_value=nullcontext()):
                    result=engine.execute(master,job)
                self.assertEqual(collector.call_count,int(recovered))
                self.assertEqual(result['status'],'Unable to Confirm' if recovered else 'Site Not Reachable')
                self.assertFalse(result['success']);self.assertEqual(result['evidence_url'],'')
                self.assertEqual(calls[1],m.SOURCE)

if __name__=='__main__':unittest.main()
