"""Recorded identities under explicit offline source conditions; no live filings."""
import copy,json,unittest,os,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from deployment import tn_extension_refresh as f,tn_extensions_demo as t
from testing.test_tn_extension_refresh import result
from testing.test_tn_extensions_demo import Accounts,ACCOUNT,NOW

KEY='test-only-key-123456789012345678901234567890'
VERSION='test-staging'
MASTER=SimpleNamespace(NY_CONNECTOR_SIGNING_KEY=KEY,APP_VERSION=VERSION)
HEADER=SimpleNamespace(headers={'Cookie':'__Host-cc_alerts='+'a'*43})
CASES=[]

class Reuse(unittest.TestCase):
    def setUp(self):
        self.a=Accounts();del self.a.extension_reference_provider
        self.s=t.Service(self.a,source_key=KEY,session_binding=f.session_binding(HEADER),source_version=VERSION)
        self.c=self.a.c;self.addCleanup(self.c.db.close)
    def test_70_recorded_cases_and_ten_main_output_controls(self):
        CASES.clear();inputs=json.loads(Path('testing/fixtures/gate53/LOCAL-70.json').read_text(encoding='utf-8'))
        for i,org in enumerate(inputs[:70]):
            r=result(org['ein'],org['name'],'CO'+str(60000+i));original=copy.deepcopy(r);mode=i%10
            if mode==6:r['renewal_filing_value']=''
            if mode==7:r['confirmation_required']=True
            if mode==8:r.update(status='Not Registered',matched_registry_identifier='',matched_registry_name='')
            if mode==9:r.update(status='Delinquent',raw_status_text='Expired')
            before=copy.deepcopy(r);token=f.issue_public_proof(MASTER,HEADER,r,NOW)
            self.assertEqual(r,before,'issuing optional proof must not change the main result')
            if mode==1:token=token[:-1]+('a' if token[-1:]!='a' else 'b')
            if mode==3:self.s.session_binding='wrong-session'
            else:self.s.session_binding=f.session_binding(HEADER)
            identifier=org['ein'] if mode!=4 else '999999999'
            name=org['name'] if mode!=5 else 'Different legal name'
            at=NOW+301 if mode==2 else NOW+10
            b=self.s.dispatch(self.c,ACCOUNT,dict(action='begin-check',ein=identifier,name=name,source_token=token),at)
            expected=mode in [0,8,9]
            self.assertEqual(b['reuse_public'],expected,(org['name'],mode))
            facts=f.facts(self.s,self.c,ACCOUNT,identifier,at)
            if expected:self.assertEqual(facts['checked_at_epoch'],NOW,'reuse must not relabel old evidence as checked now')
            else:self.assertTrue(facts['refresh_error'])
            CASES.append(dict(ein=org['ein'],name=org['name'],mode=mode,reused=expected,passed=True,conditions='Offline recorded identity with constructed main-source conditions'))
        self.assertEqual(len({x['ein'] for x in CASES}),70)
    def test_missing_key_or_cookie_and_wrong_version_cannot_reuse(self):
        for master,handler in [(SimpleNamespace(NY_CONNECTOR_SIGNING_KEY=''),HEADER),(MASTER,SimpleNamespace(headers={}))]:
            self.assertEqual(f.issue_public_proof(master,handler,result(),NOW),'')
        token=f.issue_public_proof(MASTER,HEADER,result(),NOW)
        self.s.source_version='different-release'
        self.assertFalse(self.s.dispatch(self.c,ACCOUNT,dict(action='begin-check',ein='680412350',name=result()['organization_name'],source_token=token),NOW)['reuse_public'])
    def test_stale_reuse_does_not_extend_source_age_or_retain_declaration(self):
        r=result();token=f.issue_public_proof(MASTER,HEADER,r,NOW)
        p=dict(action='begin-check',ein=r['ein'],name=r['organization_name'],source_token=token)
        self.s.dispatch(self.c,ACCOUNT,p,NOW+10)
        self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=r['ein'],answer='no'),NOW+10)
        self.assertTrue(self.s.dispatch(self.c,ACCOUNT,dict(action='status',ein=r['ein']),NOW+10)['eligibility']['eligible'])
        self.s.dispatch(self.c,ACCOUNT,p,NOW+20)
        self.assertIsNone(self.s.checked_facts(self.c,ACCOUNT,r['ein'],NOW+20)['existing_filing'])
        self.s.dispatch(self.c,ACCOUNT,p,NOW+301)
        self.assertFalse(self.s.checked_facts(self.c,ACCOUNT,r['ein'],NOW+301)['identity_verified'])
    def test_actual_staging_handler_attaches_only_to_main_tennessee_response(self):
        from deployment.performance_lab import build_handler
        class Base:
            def _send_json(self,status,payload,headers=None):return status,payload,headers
        master=SimpleNamespace(RegistrySnapshotHandler=Base,NY_CONNECTOR_SIGNING_KEY=KEY,APP_VERSION=VERSION)
        cls=build_handler(master,'test');handler=object.__new__(cls);handler.headers=HEADER.headers;handler.path='/api/final-four-connector'
        payload={'phase':'complete','result':result()};original=copy.deepcopy(payload)
        with patch.dict(os.environ,{'CE_PERMANENT_STAGING':'1'}):
            status,body,_=handler._send_json(200,payload)
            self.assertIn('extension_source_token',body['result']);self.assertEqual(payload,original)
            inputs=json.loads(Path('testing/fixtures/gate53/LOCAL-70.json').read_text(encoding='utf-8'))
            for org in inputs[:10]:
                control={'phase':'complete','result':result(org['ein'],org['name'])}
                actual=handler._send_json(200,control)[1]
                self.assertTrue(actual['result'].pop('extension_source_token'))
                self.assertEqual(actual,control)
            with patch.object(f,'issue_public_proof',side_effect=RuntimeError('optional proof failure')):
                self.assertEqual(handler._send_json(200,payload)[1],payload)

            for state in ['AL','NV','FL','NC','NY']:
                other={'phase':'complete','result':result()|{'state':state}}
                self.assertEqual(handler._send_json(200,other)[1],other)
            handler.path='/api/tn-extension-source'
            self.assertEqual(handler._send_json(200,payload)[1],payload)
    def test_70_classifications_equal_prior_build(self):
        baseline={}
        source=subprocess.check_output(['git','show','0c91adf:deployment/tn_extension_refresh.py']).decode('utf-8')
        exec(compile(source,'prior_tn_extension_refresh.py','exec'),baseline)
        inputs=json.loads(Path('testing/fixtures/gate53/LOCAL-70.json').read_text(encoding='utf-8'))
        for i,org in enumerate(inputs[:70]):
            r=result(org['ein'],org['name'],'CO'+str(60000+i))
            if i%3==1:r.update(raw_status_text='Expired',status='Delinquent')
            if i%3==2:r.update(status='Not Registered',matched_registry_identifier='',matched_registry_name='')
            self.assertEqual(f.result_facts(r,org['ein'],NOW),baseline['result_facts'](r,org['ein'],NOW))

if __name__=='__main__':unittest.main()
