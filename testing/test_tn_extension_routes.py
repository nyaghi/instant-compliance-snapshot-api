"""First/second extension routing: recorded identities, synthetic conditions.

No live source adjudication and no external filing services are used.
"""
import ast,copy,json,subprocess,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from deployment import tn_extensions_demo as t
from testing.test_tn_extensions_demo import Accounts,ACCOUNT,NOW

CASES=[]
class Routes(unittest.TestCase):
    def setUp(self):
        self.a=Accounts();self.c=self.a.c;self.s=t.Service(self.a);self.addCleanup(self.c.db.close)
    def prepare(self,identifier='680412350'):
        self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=identifier,answer='no'),NOW)
        return self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein=identifier),NOW)
    def submit(self,r):
        return self.s.dispatch(self.c,ACCOUNT,dict(action='submit',id=r['id'],fields={'coid':r['facts']['coid']},prior_filing='no',reviewed=True,authorized=True,test_response='immediate'),NOW)
    def test_70_recorded_inputs_both_routes_and_prior_build_comparison(self):
        CASES.clear();inputs=json.loads(Path('testing/fixtures/gate53/LOCAL-70.json').read_text(encoding='utf-8'))
        inputs=[dict(ein='680412350',name='Foundation for California Community Colleges')]+[x for x in inputs if x['ein']!='680412350']
        original=t.public_facts
        previous=subprocess.check_output(['git','show','36820f0045d94afd2289c84917e26d5a080ee173:deployment/tn_extensions_demo.py'],text=True,encoding='utf-8')
        node=next(n for n in ast.parse(previous).body if isinstance(n,ast.FunctionDef) and n.name=='eligibility')
        namespace=dict(day=t.day,Invalid=t.Invalid);exec(compile(ast.Module(body=[node],type_ignores=[]),'<RU eligibility>','exec'),namespace)
        for i,org in enumerate(inputs[:70]):
            self.setUp() # Each identity has an isolated test account/database.
            facts=original('680412350');facts.update(ein=org['ein'],name=org['name'],coid='CO'+str(600000+i))
            with patch.object(t,'public_facts',return_value=copy.deepcopy(facts)):
                first=self.prepare(org['ein'])
                self.assertTrue(first['eligibility']['eligible']);self.assertFalse(first['federal_required']);self.assertIsNone(first['federal_check'])
                self.assertEqual(first['support']['kind'],'first-request');self.assertNotIn('federal_searched_at',first)
                count=self.c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n']
                again=self.s.dispatch(self.c,ACCOUNT,dict(action='prepare-first',id=first['id']),NOW)
                self.assertEqual(again['documents'],first['documents']);self.assertEqual(count,self.c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n'])
                for action in ['irs-draft','irs-submit']:
                    with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action=action,id=first['id']),NOW)
                self.assertEqual(namespace['eligibility'](first['facts'],date(2026,11,18))['eligible'],first['eligibility']['eligible'])
                submitted=self.submit(first);self.assertEqual(submitted['status'],'Receipt acknowledged');self.assertNotIn('irs_submission',submitted)
                second=self.s.create(self.c,ACCOUNT,dict(ein=org['ein'],name=org['name'],scenario='second-open'),NOW)
                self.assertTrue(second['federal_required']);self.assertEqual(second['eligibility_explanation']['maximum_days'],60)
                with self.assertRaises(t.Invalid):self.submit(second)
                attached=self.s.dispatch(self.c,ACCOUNT,dict(action='attach-demo-evidence',id=second['id']),NOW)
                self.assertEqual(self.submit(attached)['status'],'Receipt acknowledged')
                CASES.append(dict(name=org['name'],ein=org['ein'],first_state_eligibility_unchanged_from_RU=True,
                    intended_difference='First submits without federal evidence; second requires accepted federal evidence',
                    first_passed=True,second_passed=True,conditions='Synthetic filing conditions; offline recorded identity replay, not independent source verification'))
        self.assertEqual(len({r['ein'] for r in CASES}),70)
    def test_second_missing_grant_or_invalid_extended_deadline_blocks(self):
        for change in [dict(first_extension_granted_verified=False),dict(original_expiration=''),dict(expiration='2027-06-01'),dict(second_extension_verified=False),dict(return_type='990-N')]:
            facts=t.demo_facts('440610626','Synthetic','second-open');facts.update(change)
            self.assertFalse(t.eligibility(facts,date(2026,11,18))['eligible'])
    def test_second_expired_federal_window_no_draft_but_existing_proof_allowed(self):
        r=self.s.create(self.c,ACCOUNT,dict(ein='440610626',name='Synthetic',scenario='second-open'),NOW)
        raw=self.s.load(self.c,ACCOUNT,r['id']);raw['facts'].update(period_start='2025-07-01',period_end='2026-06-30')
        self.s.save(self.c,ACCOUNT,raw,NOW)
        for action in ['irs-draft','irs-submit']:
            with self.assertRaisesRegex(t.Invalid,'deadline has passed'):self.s.dispatch(self.c,ACCOUNT,dict(action=action,id=r['id']),NOW)
        self.assertNotIn('irs_draft',self.s.load(self.c,ACCOUNT,r['id'])['documents'])
        attached=self.s.dispatch(self.c,ACCOUNT,dict(action='attach-demo-evidence',id=r['id']),NOW)
        self.assertEqual(self.submit(attached)['status'],'Receipt acknowledged')
    def test_stage_cannot_be_selected_by_request_payload(self):
        r=self.prepare()
        for action in ['irs-draft','irs-submit']:
            with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action=action,id=r['id'],extension_number=2),NOW)
    def test_first_existing_federal_artifacts_preserved_during_upgrade(self):
        r=self.prepare();raw=self.s.load(self.c,ACCOUNT,r['id']);raw['workflow_version']=3
        originals=dict(raw['documents']);raw['documents']['irs_draft']='old-federal-document'
        self.s.save(self.c,ACCOUNT,raw,NOW)
        migrated=self.s.load(self.c,ACCOUNT,r['id']);self.assertEqual(migrated['documents'],originals|{'irs_draft':'old-federal-document'})
        self.assertEqual(migrated['workflow_version'],4);self.assertEqual(self.submit(migrated)['status'],'Receipt acknowledged')
    def test_first_existing_irs_evidence_is_an_alternative_not_new_federal_filing(self):
        r=self.prepare();r=self.s.dispatch(self.c,ACCOUNT,dict(action='attach-demo-evidence',id=r['id']),NOW)
        self.assertEqual(r['support']['kind'],'8868');self.assertFalse(r['federal_required']);self.assertNotIn('irs_submission',r)
        self.assertEqual(self.submit(r)['status'],'Receipt acknowledged')
    def test_reason_edits_require_regeneration_without_extra_documents(self):
        r=self.prepare();before=self.c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n']
        raw=self.s.load(self.c,ACCOUNT,r['id']);raw['fields']['reason']='Waiting for audited financial statements.';self.s.save(self.c,ACCOUNT,raw,NOW)
        with self.assertRaisesRegex(t.Invalid,'Update the reason document'):self.submit(raw)
        updated=self.s.dispatch(self.c,ACCOUNT,dict(action='prepare-first',id=r['id'],reason=raw['fields']['reason']),NOW)
        self.assertEqual(updated['support']['url'],r['support']['url']);self.assertEqual(before,self.c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n'])
        self.assertEqual(updated['support']['reason'],raw['fields']['reason']);self.assertEqual(self.submit(updated)['status'],'Receipt acknowledged')
    def test_returned_email_outcome_is_distinct_from_receipt_and_approval(self):
        r=self.prepare();payload=dict(action='submit',id=r['id'],fields={'coid':r['facts']['coid']},prior_filing='no',reviewed=True,authorized=True,test_response='returned')
        d=self.s.dispatch(self.c,ACCOUNT,payload,NOW)
        self.assertEqual(d['status'],'Receipt acknowledged');self.assertEqual(d['state_review']['outcome'],'Returned for correction')
        self.assertIn('NOT approved',d['approval']);self.assertIn('state_response',d['documents'])
        repeated=self.s.dispatch(self.c,ACCOUNT,payload,NOW+30);self.assertEqual(repeated['state_sends'],1);self.assertEqual(repeated['documents'],d['documents'])

if __name__=='__main__':unittest.main()
