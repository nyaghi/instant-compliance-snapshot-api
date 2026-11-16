"""Offline retry-history and late ND capture regression checks."""
import io, time, unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
import registry_snapshot_server as c
from deployment import state_snapshots as ss, search_history as sh, nd_candidate_evidence as nd

class MichiganHistory(unittest.TestCase):
    def test_same_run_receipts_survive_empty_second_attempt(self):
        calls=[]
        def source(name,ein,state,*args):
            calls.append(ss.CURRENT.get().run_id)
            if len(calls)==1:
                sh.begin_source_query(state,name,'Name','https://www.ag.state.mi.us/CharitableTrust/').complete(0,[])
                status='Site Not Reachable'
            else: status='Not Registered'
            return dict(organization_name=name,ein=ein,state=state,status=status,success=status=='Not Registered',source_url='https://www.ag.state.mi.us/CharitableTrust/')
        def retry(name,ein,state):
            c.run_state_lookup(name,ein,state)
            return c.run_state_lookup(name,ein,state)
        token=c.LAB_LOOKUP_MODE_CONTEXT.set('standard')
        try:
            with patch.object(c,'trial_identity',return_value=True), patch.object(c,'known_names_for_ein',return_value=[]), patch.object(c,'_run_single_state_lookup_reliably_source',side_effect=retry), patch.object(c,'_run_state_lookup_source',side_effect=source), patch('deployment.source_visual_adapters.capture_result_visuals'), patch.object(ss,'downloaded_record'), patch.dict(c.os.environ,{'CE_FINAL_FOUR_CHILD':'1'}), patch('deployment.group_identity_review.recover',side_effect=lambda m,d,f:d) as recover:
                data=c.run_single_state_lookup_reliably('Test Charity','123456789','MI')
            self.assertEqual(data['status'],'Not Registered')
            self.assertEqual(len(calls),2)
            self.assertEqual(len(set(calls)),1)
            history=data['_worker_search_history']
            self.assertEqual(history['ein'],'123456789')
            self.assertEqual(len(history['completed']),1)
            self.assertEqual(history['completed'][0]['query']['name'],'Test Charity')
            recover.assert_called_once()
            self.assertIsNone(ss.CURRENT.get())
        finally: c.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_different_identity_does_not_reuse_capture(self):
        for state,ein,name in [('MI','987654321','Test Charity'),('MI','123456789','Other Charity'),('WI','123456789','Test Charity')]:
            observed=[]
            with ss.CaptureRun('Test Charity','123456789','MI') as outer:
                outer.semantic_history_scope=True
                def source(*a):
                    observed.append(ss.CURRENT.get().run_id)
                    return dict(organization_name=name,ein=ein,state=state,status='Site Not Reachable')
                with patch.object(c,'trial_identity',return_value=True), patch.object(c,'known_names_for_ein',return_value=[]), patch.object(c,'_run_state_lookup_source',side_effect=source), patch('deployment.source_visual_adapters.capture_result_visuals'), patch.object(ss,'downloaded_record'), patch.dict(c.os.environ,{'CE_FINAL_FOUR_CHILD':'1'}):
                    c.run_state_lookup(name,ein,state)
                self.assertNotEqual(observed,[outer.run_id])

class NorthDakotaCapture(unittest.TestCase):
    def run_capture(self, *, remaining=-1, task=100, changed=False, route=True, existing=None, blocked=False):
        clock=[100.0]; blob=io.BytesIO(); Image.new('RGB',(800,900),'white').save(blob,format='JPEG')
        raw=blob.getvalue(); run=SimpleNamespace(state='ND',visual_adapter_facts=[],capture_ms=0,documents=[])
        if existing is not None: run.nd_review_capture_stop=existing
        run.document=lambda url,data,*a,**k:run.documents.append((url,data))
        page=Mock(); page.url='https://firststop.sos.nd.gov/search/charitable' if route else 'https://other.test/'
        expected={'name':'Test Charity','id':'0000000001','fields':{'Status':'Active'}}
        page.evaluate.side_effect=[expected,{} if changed else expected]
        def wait(*a,timeout,**k):
            if blocked:
                clock[0]+=timeout/1000
                raise TimeoutError('not ready')
            clock[0]+=.1
        page.wait_for_function.side_effect=wait
        page.inner_text.return_value='Test Charity 0000000001 Active'
        page.screenshot.return_value=raw
        t=ss.CURRENT.set(run); d=ss.DEADLINE.set(100+task)
        try:
            with patch.object(nd.time,'monotonic',side_effect=lambda:clock[0]),patch.object(nd.time,'perf_counter',side_effect=lambda:clock[0]):
                nd.capture(page,{'TITLE':['Test Charity'],'RECORD_NUM':'0000000001'},{'Status':'Active'},100+remaining)
        finally: ss.CURRENT.reset(t);ss.DEADLINE.reset(d)
        return run,page,clock[0]-100

    def test_open_detail_after_search_deadline_is_captured_without_navigation(self):
        run,page,elapsed=self.run_capture()
        self.assertEqual(run.visual_adapter_facts[0]['outcome'],'captured')
        self.assertLessEqual(run.nd_review_capture_stop,103)
        page.goto.assert_not_called()
        self.assertLess(elapsed,3)

    def test_global_and_shared_deadlines_still_apply(self):
        for kwargs in [{'task':2},{'existing':101},{'route':False}]:
            run,page,_=self.run_capture(**kwargs)
            self.assertEqual(run.documents,[]);page.screenshot.assert_not_called()

    def test_changed_record_is_not_published(self):
        run,_,_=self.run_capture(changed=True)
        self.assertEqual(run.documents,[])
        self.assertEqual(run.visual_adapter_facts[0]['outcome'],'source_changed')

    def test_unready_detail_has_one_bounded_wait(self):
        run,page,elapsed=self.run_capture(blocked=True)
        self.assertEqual(run.documents,[]);page.wait_for_function.assert_called_once()
        self.assertLessEqual(elapsed,1)

    def test_healthy_existing_allowance_is_unchanged(self):
        run,_,_=self.run_capture(remaining=8)
        self.assertEqual(run.nd_review_capture_stop,108)

if __name__=='__main__':unittest.main()
