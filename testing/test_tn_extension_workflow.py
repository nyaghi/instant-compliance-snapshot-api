"""Offline TN workflow checks. Organization inputs are real recorded names/EINs;
eligibility variations are explicitly synthetic, not 70 live source verdicts.
"""
import copy,io,json,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader
from testing.test_tn_extensions_demo import Accounts,ACCOUNT,OTHER,NOW
from deployment import tn_extensions_demo as t
from deployment import tn_extension_documents as federal

CASES=[]
class Workflow(unittest.TestCase):
    def setUp(self):
        self.a=Accounts();self.c=self.a.c;self.s=t.Service(self.a);self.addCleanup(self.c.db.close)
    def prepare(self,identifier='440610626'):
        self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=identifier,answer='no'),NOW)
        return self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein=identifier),NOW)
    def irs(self,r):
        # Federal contracts exercise a separately verified synthetic SECOND
        # extension, never the public first-extension candidate.
        r=self.s.create(self.c,ACCOUNT,dict(ein=r['ein'],name=r['facts']['name'],scenario='second-open'),NOW)
        return self.s.dispatch(self.c,ACCOUNT,dict(action='irs-submit',id=r['id'],federal_fields=r['federal_fields']|dict(books='Demo Custodian',phone='202-555-0100',tax_a='0',tax_b='0',tax_c='0'),reviewed=True,authorized=True),NOW)
    def submit(self,r,behavior='delayed'):
        return self.s.dispatch(self.c,ACCOUNT,dict(action='submit',id=r['id'],fields={'coid':r['facts']['coid']},prior_filing='no',reviewed=True,authorized=True,test_response=behavior),NOW)
    def test_reported_fcc_first_request_does_not_require_federal_draft(self):
        r=self.prepare('680412350')
        self.assertIsNone(r['federal_check']);self.assertEqual(r['support']['kind'],'first-request')
        for action in ['irs-draft','irs-submit']:
            with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action=action,id=r['id']),NOW)
        self.assertEqual(self.submit(r,'immediate')['status'],'Receipt acknowledged')
        self.assertEqual(r['eligibility_explanation']['maximum_requested_date'],'2027-03-31')
    def test_eligible_no_path_both_test_submissions_and_matching_receipt(self):
        r=self.irs(self.prepare());self.assertTrue(r['support']['accepted'])
        d=self.submit(r);self.assertEqual(d['status'],'Extension submitted')
        self.assertNotIn('acknowledgment',d['documents'])
        d=self.s.dispatch(self.c,ACCOUNT,dict(action='receipt',id=d['id']),NOW+16)
        self.assertEqual(d['status'],'Receipt acknowledged');self.assertTrue(d['acknowledgment_provenance']['demo_only'])
        self.assertEqual(d['acknowledgment_provenance']['source'],'Isolated Tennessee test service')
        self.assertEqual(d['state_sends'],1);self.assertEqual(d['irs_submission']['sends'],1)
        for key in ['irs_filed','irs_acceptance','application','acknowledgment']:
            raw=self.c.execute('SELECT body FROM cc_tn_extension_demo_documents WHERE id=%s',(d['documents'][key].rsplit('/',1)[-1],)).fetchone()['body']
            self.assertIn('DEMO ONLY',' '.join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages).upper())
    def test_time_alone_cannot_acknowledge_missing_or_mismatched_provider_record(self):
        for mutation in ['missing','account','source','confirmation','application_sha256','period_end','demo_only','available_at']:
            with self.subTest(mutation=mutation):
                self.setUp()
                d=self.submit(self.irs(self.prepare()));stored=self.s.load(self.c,ACCOUNT,d['id'])
                if mutation=='missing':stored['gateway'].pop('receipt')
                else:stored['gateway']['receipt'][mutation]='wrong'
                self.s.save(self.c,ACCOUNT,stored,NOW)
                later=self.s.dispatch(self.c,ACCOUNT,dict(action='receipt',id=d['id']),NOW+3600)
                self.assertEqual(later['status'],'Extension submitted');self.assertNotIn('acknowledgment',later['documents'])
    def test_timeout_reconciles_after_restart_without_second_send(self):
        d=self.submit(self.irs(self.prepare()),'timeout');self.assertEqual(d['status'],'Submission unconfirmed')
        with self.assertRaises(t.Conflict):self.submit(d)
        fresh=t.Service(self.a);later=fresh.dispatch(self.c,ACCOUNT,dict(action='status',ein=d['ein']),NOW+16)['requests'][0]
        self.assertEqual(later['status'],'Receipt acknowledged');self.assertEqual(later['state_sends'],1)
        self.assertEqual(later['documents']['application'],d['documents']['application'])
        self.assertEqual(self.submit(later)['documents'],later['documents'])
        self.assertEqual(fresh.existing(self.c,OTHER,d['ein']),[])
    def test_990n_and_unverified_period_do_not_prepare_draft(self):
        for change in [dict(return_type='990-N'),dict(return_type='1041'),dict(period_start='2026-01-01')]:
            r=self.prepare();raw=self.s.load(self.c,ACCOUNT,r['id']);raw['facts'].update(change);self.s.save(self.c,ACCOUNT,raw,NOW)
            with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action='irs-draft',id=r['id']),NOW)
    def test_confirmation_capture_is_bound_protected_and_idempotent(self):
        import base64
        from PIL import Image
        d=self.submit(self.irs(self.prepare()),'immediate')
        png=io.BytesIO();Image.new('RGB',(620,400),'white').save(png,format='PNG')
        payload=dict(action='capture-confirmation',id=d['id'],confirmation=d['confirmation'],application_sha256=d['application_sha256'],body=base64.b64encode(png.getvalue()).decode())
        with self.assertRaises(t.Invalid):self.s.dispatch(self.c,OTHER,payload,NOW)
        for change in [dict(confirmation='WRONG'),dict(application_sha256='WRONG'),dict(body='!!!!')]:
            with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,payload|change,NOW)
        first=self.s.dispatch(self.c,ACCOUNT,payload,NOW);second=self.s.dispatch(self.c,ACCOUNT,payload,NOW+10)
        self.assertEqual(first['documents'],second['documents']);self.assertEqual(second['state_sends'],1)
        raw=self.c.execute('SELECT body FROM cc_tn_extension_demo_documents WHERE id=%s',(first['documents']['confirmation_screen'].rsplit('/',1)[-1],)).fetchone()['body']
        text=' '.join(p.extract_text() for p in PdfReader(io.BytesIO(raw)).pages)
        self.assertIn('CAPTURE OF CHARITYCLARITY TEST CONFIRMATION',text)
        self.assertIn('Not a screenshot of the Tennessee website',text)
    def test_70_recorded_org_inputs_with_explicit_synthetic_conditions(self):
        CASES.clear();inputs=json.loads(Path('testing/fixtures/gate53/LOCAL-70.json').read_text(encoding='utf-8'))
        reported=[dict(ein='680412350',name='Foundation for California Community Colleges'),dict(ein='521273585',name='Global Impact'),dict(ein='440610626',name='Fellowship of Christian Athletes')]
        inputs=reported+[x for x in inputs if x['ein'] not in {y['ein'] for y in reported}];inputs=inputs[:70]
        self.assertEqual(len({x['ein'] for x in inputs}),70)
        original=t.public_facts
        for i,org in enumerate(inputs):
            facts=original('440610626');facts.update(ein=org['ein'],name=org['name'],coid='DEMO-CO'+str(i),existing_filing=False)
            mode=i%7
            if mode==0:facts.update(period_start='2025-07-01',period_end='2026-06-30',expiration='2026-12-31')
            if mode==1:facts['expiration']='2026-11-17'
            if mode==2:facts['existing_filing']=True
            if mode==3:facts['existing_filing']=None
            if mode==4:facts['period_verified']=False
            if mode==5:facts['return_type']='990-N'
            state=t.eligibility(facts,date(2026,11,18));f=federal.federal_status(facts,date(2026,11,18));e=t.eligibility_explanation(facts,date(2026,11,18))
            self.assertEqual(state['eligible'],mode in [0,5,6]);self.assertEqual(f['eligible'],mode not in [0,5]);self.assertEqual(f['can_prepare'],mode!=5)
            self.assertTrue(e['approval_required'])
            CASES.append(dict(organization=org['name'],ein=org['ein'],mode=mode,state_eligible=state['eligible'],federal_eligible=f['eligible'],draftable=f['can_prepare'],conditions='Synthetic eligibility conditions on recorded organization identity; not live registry adjudication',passed=True))
    def test_replace_obsolete_test_capture_without_duplicate_or_filing_changes(self):
        import base64
        from PIL import Image
        d=self.submit(self.irs(self.prepare()),'immediate');image=io.BytesIO();Image.new('RGB',(620,400),'white').save(image,format='PNG')
        payload=dict(action='capture-confirmation',id=d['id'],confirmation=d['confirmation'],application_sha256=d['application_sha256'],body=base64.b64encode(image.getvalue()).decode())
        first=self.s.dispatch(self.c,ACCOUNT,payload,NOW);stored=self.s.load(self.c,ACCOUNT,d['id']);stored['confirmation_capture']['format_version']=1;self.s.save(self.c,ACCOUNT,stored,NOW)
        before=self.c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n']
        second=self.s.dispatch(self.c,ACCOUNT,payload,NOW+1)
        self.assertNotEqual(second['documents']['confirmation_screen'],first['documents']['confirmation_screen'])
        self.assertEqual(self.c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n'],before)
        for kind in ['application','acknowledgment','irs_filed','irs_acceptance']:self.assertEqual(second['documents'][kind],first['documents'][kind])
        self.assertEqual(second['confirmation_capture']['format_version'],2);self.assertEqual(second['state_sends'],1)

if __name__=='__main__':unittest.main()
