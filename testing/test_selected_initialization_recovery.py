"""Blank bootstrap recovery shares the original stop and one passive observer."""
import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from deployment import source_visual_adapters as a

def boundary(host='ca-rcf.evokeplatform.com'):
    return {'route_matches':True,'terminal_read':'completed','failed':0,'errors':[],
      'pending_overflow':0,'elapsed_seconds':29,'pending':[{'host':host,'path':'/api/webContent/themes','type':'xhr','age_seconds':23}],
      'terminal':{'document_state':'complete','body_text_chars':0,'form_count':0,'expected_name_present':False,'expected_id_present':False,'verification_present':False,'error_present':False}}

class InitializationRecovery(unittest.TestCase):
    def setUp(self):
        self.clock=[29.0];self.url='https://ca-rcf.evokeplatform.com/app/publicPortal/registrationDetails/1006488'
        self.master=SimpleNamespace(trial_identity=lambda:True,LAB_LOOKUP_MODE_CONTEXT=SimpleNamespace(get=lambda:'standard'))
        self.page=Mock(url=self.url);self.page.reload.return_value=SimpleNamespace(status=200)
        self.fact={'adapter':'CA-selected-registration-detail','initialization_boundary_observation':boundary(),'initialization_continuation':{'count':1}}
        p=patch.object(a.time,'monotonic',side_effect=lambda:self.clock[0]);p.start();self.addCleanup(p.stop)
    def test_single_same_detail_reload_has_no_new_clock_or_query(self):
        for i in range(30):
            self.page.reset_mock();self.fact.pop('initialization_reload',None)
            a.retry_selected_blank_initialization(self.master,self.page,self.fact,self.url,44)
            self.page.reload.assert_called_once_with(wait_until='commit',timeout=5000)
            self.assertEqual(self.fact['initialization_reload']['count'],1)
            a.retry_selected_blank_initialization(self.master,self.page,self.fact,self.url,44)
            self.page.reload.assert_called_once();self.page.goto.assert_not_called()
    def test_fast_or_started_body_challenge_error_failed_or_answered_dependency_never_reloads(self):
        changes=[('body_text_chars',1),('form_count',1),('expected_name_present',True),('expected_id_present',True),('verification_present',True),('error_present',True),('document_state','loading')]
        cases=[]
        for key,value in changes:
            obs=boundary();obs['terminal'][key]=value;cases.append(obs)
        for key,value in [('failed',1),('errors',[{'kind':'TypeError'}]),('route_matches',False),('pending_overflow',1),('terminal_read','unavailable')]:
            obs=boundary();obs[key]=value;cases.append(obs)
        for change in [{'status':200},{'age_seconds':19},{'path':'/unrelated'},{'host':'other.example'}]:
            obs=boundary();obs['pending'][0].update(change);cases.append(obs)
        for obs in cases:
            fact={**self.fact,'initialization_boundary_observation':obs}
            a.retry_selected_blank_initialization(self.master,self.page,fact,self.url,44)
        self.page.reload.assert_not_called()
    def test_parent_cutoff_changed_route_and_sales_nontrial_paths_do_not_reload(self):
        a.retry_selected_blank_initialization(self.master,self.page,self.fact,self.url,36)
        self.page.url='https://other.example';a.retry_selected_blank_initialization(self.master,self.page,self.fact,self.url,44);self.page.url=self.url
        self.master.trial_identity=lambda:None;a.retry_selected_blank_initialization(self.master,self.page,self.fact,self.url,44)
        self.master.trial_identity=lambda:True;self.master.LAB_LOOKUP_MODE_CONTEXT.get=lambda:'sales';a.retry_selected_blank_initialization(self.master,self.page,self.fact,self.url,44)
        self.page.reload.assert_not_called()
    def test_unconfirmed_reload_response_cannot_become_an_accepted_capture(self):
        for status in [403,429,503]:
            self.fact.pop('initialization_reload',None);self.page.reload.return_value=SimpleNamespace(status=status)
            with self.assertRaises(ValueError):a.retry_selected_blank_initialization(self.master,self.page,self.fact,self.url,44)
    def test_pending_request_finishes_after_checkpoint_without_losing_observation(self):
        for i in range(30):
            self.clock[0]=0;listeners={};page=Mock(url=self.url)
            page.on.side_effect=lambda event,callback:listeners.update({event:callback})
            page.locator.return_value.evaluate.return_value=boundary()['terminal']
            fact={'adapter':'CA-selected-registration-detail'}
            finish=a.observe_selected_readiness(page,fact,self.url,'Example Relief','1006488',30)
            req=SimpleNamespace(url='https://ca-rcf.evokeplatform.com/api/webContent/themes?private=not-retained',resource_type='xhr')
            # Playwright requests are identity-hashable.
            class Request:
                url=req.url;resource_type='xhr'
            req=Request();listeners['request'](req);self.clock[0]=29;finish.checkpoint()
            page.remove_listener.assert_not_called();self.assertEqual(fact['selected_readiness_observation']['pending_count'],1)
            frozen=json.loads(json.dumps(fact['selected_readiness_observation']))
            finish.continue_until(45);self.clock[0]=34
            listeners['response'](SimpleNamespace(request=req,status=200));listeners['requestfinished'](req)
            finish();obs=fact['selected_readiness_observation']
            self.assertEqual((obs['requests'],obs['finished'],obs['pending_count']),(1,1,0));self.assertEqual(obs['remaining_seconds'],11)
            self.assertEqual(frozen['pending_count'],1);self.assertNotIn('private',json.dumps(obs))
            self.assertEqual(page.remove_listener.call_count,5);finish();self.assertEqual(page.remove_listener.call_count,5)

if __name__=='__main__':unittest.main()
