"""70 distinct synthetic TN inputs plus workflow/security regression contracts.

These are local offline tests, not 70 live state searches or independent legal
adjudications. Existing state adapters and registry search plans are unchanged.
"""
import ast
import copy
from contextlib import contextmanager
from datetime import date
import io
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from psycopg.types.json import Jsonb
from deployment import tn_extensions_demo as t

ACCOUNT='pilot@example.org';OTHER='other@example.org';NOW=1795017600
CASE_RESULTS=[]
REFERENCE_RESULTS=[]

class Connection:
    def __init__(self):
        self.db=sqlite3.connect(':memory:')
        def rows(cursor,values):
            row=dict(zip((col[0] for col in cursor.description),values))
            if isinstance(row.get('data'),str):row['data']=json.loads(row['data'])
            return row
        self.db.row_factory=rows
        self.db.executescript(t.SCHEMA)
    def execute(self,q,p=()):
        if q==t.SCHEMA:return None
        if q.startswith('SELECT pg_advisory'):return self.db.execute('SELECT 1')
        return self.db.execute(q.replace('%s','?').replace(' FOR UPDATE',''),tuple(json.dumps(x.obj) if isinstance(x,Jsonb) else x for x in p))

class Accounts:
    def __init__(self):self.c=Connection()
    @contextmanager
    def transaction(self):
        with self.c.db:yield self.c
    def account(self,c,h):return h.headers.get('Test-Account')

class Handler:
    def __init__(self,p=None,account=ACCOUNT,origin='https://staging.example',path=t.PREFIX):
        raw=json.dumps(p).encode() if p is not None else b''
        self.path=path;self.command='POST' if p is not None else 'GET';self.rfile=io.BytesIO(raw);self.wfile=io.BytesIO();self.sent={}
        self.headers={'Content-Length':str(len(raw)),'Content-Type':'application/json','Origin':origin,'Test-Account':account}
    def _send_json(self,status,p,headers):return status,p,headers
    def send_response(self,status):self.status=status
    def send_header(self,k,v):self.sent[k]=v
    def end_headers(self):pass

class Tests(unittest.TestCase):
    def setUp(self):
        self.a=Accounts();self.c=self.a.c;self.s=t.Service(self.a);self.addCleanup(self.c.db.close)
    def create(self,scenario='open',identifier='012345678'):
        return self.s.create(self.c,ACCOUNT,dict(ein=identifier,name='Demo Foundation',scenario=scenario),NOW)
    def payload(self,r,**overrides):
        return dict(fields=r['fields']|dict(contact='Test Filer',contact_email='filer@example.org',title='Authorized Agent',reason='Additional time to finalize the financial report.'),prior_filing='no',reviewed=True,authorized=True,test_response='delayed')|overrides
    def submit(self,r,**kw):return self.s.submit(self.c,ACCOUNT,self.s.load(self.c,ACCOUNT,r['id']),self.payload(r,**kw),NOW)
    def test_70_distinct_organization_eligibility_inputs(self):
        CASE_RESULTS.clear()
        for i in range(70):
            identifier=str(100000000+i);f=t.demo_facts(identifier,'Offline Organization '+str(i),'open');expected=True
            case=i%14
            if case<5:
                key=['identity_verified','current_verified','period_verified','expiration_verified','first_extension_verified'][case];f[key]=False;expected=False
            elif case==5:f['existing_filing']=True;expected=False
            elif case==6:f['existing_filing']=None;expected=False
            elif case==7:f['expiration']='2026-11-17';expected=False
            elif case==8:f['period_start']='2026-07-01';expected=False
            elif case==9:f['period_end']='2027-01-01';expected=False
            elif case==10:f['expiration']='';expected=False
            elif case==11:f['expiration']='2026-11-18' # on-deadline first request
            elif case==12:f['expiration']='2026-11-19'
            with self.subTest(organization=identifier,case=case):
                actual=t.eligibility(f,date(2026,11,18));self.assertEqual(actual['eligible'],expected)
                CASE_RESULTS.append(dict(ein=identifier,case=case,expected=expected,result=actual))
        self.assertEqual(len({x['ein'] for x in CASE_RESULTS}),70)
    def test_open_closed_existing_unverified(self):
        for scenario,expected in [('open',True),('closed',False),('already-filed',False),('unverified',False)]:
            r=self.create(scenario);self.assertEqual(r['eligibility']['eligible'],expected)
            if not expected:
                with self.assertRaises(t.Invalid):self.submit(r)
    def test_unknown_prior_filing_is_not_absence(self):
        r=self.create()
        for answer in ['unknown','yes']:
            with self.assertRaises(t.Invalid):self.submit(r,prior_filing=answer)
    def test_missing_review_authority_and_required_fields(self):
        r=self.create()
        for p in [dict(reviewed=False),dict(authorized=False),dict(fields=r['fields']),dict(fields=self.payload(r)['fields']|dict(contact_email='broken'))]:
            with self.assertRaises(t.Invalid):self.submit(r,**p)
    def test_identity_edits_need_reverification(self):
        r=self.create()
        with self.assertRaises(t.Invalid):self.submit(r,fields=self.payload(r)['fields']|dict(coid='OTHER'))
    def test_requested_days_limits(self):
        for x in ['0','91','-1','abc','1.5']:
            r=self.create(identifier='01234567'+str(len(x)%10))
            with self.assertRaises(t.Invalid):self.submit(r,fields=self.payload(r)['fields']|dict(requested_days=x))
    def test_immediate_ack_is_not_approval(self):
        r=self.submit(self.create(),test_response='immediate')
        self.assertEqual(r['status'],'Receipt acknowledged');self.assertIn('Not approved',r['approval']);self.assertEqual(set(r['documents']),{'application','acknowledgment'})
    def test_delayed_ack_survives_new_service_and_rerun(self):
        r=self.submit(self.create());application=r['documents']['application']
        self.assertEqual(r['status'],'Extension submitted');self.assertNotIn('acknowledgment',r['documents'])
        fresh=t.Service(self.a);d=fresh.dispatch(self.c,ACCOUNT,dict(action='status',ein=r['ein']),NOW+16)['requests'][0]
        self.assertEqual(d['status'],'Receipt acknowledged');self.assertEqual(d['documents']['application'],application);self.assertEqual(d['state_sends'],1)
        old=copy.deepcopy(d);fresh.reconcile(self.c,ACCOUNT,fresh.load(self.c,ACCOUNT,d['id']),NOW+60)
        self.assertEqual(self.s.load(self.c,ACCOUNT,d['id'])['documents'],old['documents'])
    def test_timeout_requires_receipt_and_never_resubmits(self):
        r=self.submit(self.create(),test_response='timeout');self.assertEqual(r['status'],'Submission unconfirmed')
        with self.assertRaises(t.Conflict):self.submit(r)
        d=self.s.dispatch(self.c,ACCOUNT,dict(action='receipt',id=r['id']),NOW+16)
        self.assertEqual(d['status'],'Receipt acknowledged');self.assertEqual(d['state_sends'],1)
        self.assertEqual(self.submit(d)['state_sends'],1)
    def test_multiple_drafts_cannot_submit_same_period(self):
        a=self.create();b=self.create();self.submit(a)
        with self.assertRaises(t.Conflict):self.submit(b)
    def test_create_after_submission_reuses_existing(self):
        r=self.submit(self.create());self.assertEqual(self.create()['id'],r['id'])
    def test_receipt_mismatch_does_not_acknowledge(self):
        r=self.submit(self.create());stored=self.s.load(self.c,ACCOUNT,r['id']);stored['gateway']['ein']='999999999';self.s.save(self.c,ACCOUNT,stored,NOW)
        d=self.s.dispatch(self.c,ACCOUNT,dict(action='receipt',id=r['id']),NOW+16)
        self.assertEqual(d['status'],'Extension submitted');self.assertNotIn('acknowledgment',d['documents'])
    def test_definite_failure_preserves_editable_draft(self):
        r=self.submit(self.create(),test_response='failed');self.assertEqual(r['status'],'Submission failed');self.assertFalse(r['documents'])
        p=self.payload(r);self.s.edit(r,p);self.assertEqual(r['fields']['reason'],p['fields']['reason'])
        self.assertEqual(self.submit(r,test_response='immediate')['state_sends'],2)
    def test_account_scope_for_drafts_and_documents(self):
        r=self.submit(self.create(),test_response='immediate')
        with self.assertRaises(t.Invalid):self.s.load(self.c,OTHER,r['id'])
        self.assertEqual(self.s.existing(self.c,OTHER,r['ein']),[])
        h=Handler(account=OTHER,path=r['documents']['application']);self.assertEqual(t.handle(self.a,h,origin='https://staging.example')[0],404)
        h=Handler(account=ACCOUNT,path=r['documents']['application']);t.handle(self.a,h,origin='https://staging.example');self.assertEqual(h.status,200);self.assertTrue(h.wfile.getvalue().startswith(b'%PDF'));self.assertEqual(h.sent['Cache-Control'],'no-store')
    def test_auth_origin_and_client_fact_guards(self):
        for h,expected in [(Handler({'action':'check','ein':'012345678'},account=None),403),(Handler({'action':'create','ein':'012345678'},origin='https://evil.example'),403),(Handler({'action':'create','ein':'012345678','facts':{}}),400),(Handler({'action':'create','ein':'012345678','endpoint':'https://tncab.tnsos.gov'}),400)]:
            self.assertEqual(t.handle(self.a,h,origin='https://staging.example')[0],expected)
    def test_submission_is_immutable(self):
        r=self.submit(self.create())
        with self.assertRaises(t.Conflict):self.s.edit(r,self.payload(r))
    def test_real_facts_do_not_assert_open_window(self):
        f=t.public_facts('131610451');self.assertEqual(f['expiration'],'2026-11-27');self.assertFalse(t.eligibility(f,date(2026,11,18))['eligible'])
        self.assertFalse(t.eligibility(t.public_facts('012345678'),date(2026,11,18))['eligible'])
    def test_70_reference_records_use_generic_rules(self):
        REFERENCE_RESULTS.clear()
        for i in range(70):
            r=dict(ein=str(200000000+i),name='Reference Organization '+str(i),coid='CO'+str(i),identity_verified=True,status='Active',expiration='2026-12-31',last_reported_period='2025-06-30',checked_at='2026-11-18')
            case=i%10;expected=case==0
            if case==1:r['expiration']='2026-11-27'
            if case==2:r['last_reported_period']='2024-06-30'
            if case==3:r['last_reported_period']='2026-06-30'
            if case==4:r['checked_at']='2026-11-15'
            if case==5:r['identity_verified']=False
            if case==6:r['status']='Expired'
            if case==7:r['expiration']='2026-12-30'
            if case==8:r['last_reported_period']='2025-05-31'
            if case==9:r['checked_at']='2026-11-19'
            f=t.reference_facts(r,date(2026,11,18));f['existing_filing']=False
            actual=t.eligibility(f,date(2026,11,18))
            with self.subTest(ein=r['ein']):self.assertEqual(actual['eligible'],expected)
            REFERENCE_RESULTS.append(dict(input=r,expected=expected,result=actual))
    def test_verified_candidate_requires_filer_answer_before_prepare(self):
        d=self.s.dispatch(self.c,ACCOUNT,dict(action='check',ein='521273585'),NOW)
        self.assertTrue(d['needs_prior_confirmation']);self.assertFalse(d['eligibility']['eligible'])
        self.assertEqual(d['facts']['period_end'],'2026-06-30');self.assertEqual(d['facts']['period_start'],'2025-07-01')
        with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein='521273585'),NOW)
        yes=self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein='521273585',answer='yes'),NOW)
        self.assertFalse(yes['eligibility']['eligible'])
        no=self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein='521273585',answer='no'),NOW)
        self.assertTrue(no['eligibility']['eligible'])
        r=self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein='521273585'),NOW)
        self.assertEqual(r['fields']['coid'],'CO901');self.assertEqual(r['fields']['name'],'Global Impact');self.assertEqual(r['scenario'],'verified');self.assertEqual(r['prior_filing'],'no')
        self.assertFalse(self.s.checked_facts(self.c,OTHER,'521273585',NOW)['existing_filing'] is False)
        d=self.submit(r,test_response='immediate');self.assertEqual(d['status'],'Receipt acknowledged')
        after=self.s.dispatch(self.c,ACCOUNT,dict(action='check',ein='521273585'),NOW+1)
        self.assertFalse(after['eligibility']['eligible']);self.assertTrue(after['facts']['existing_filing'])
        self.assertIn('acknowledgment',after['requests'][0]['documents'])
    def test_verified_candidate_requires_fresh_source_at_submission(self):
        self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein='521273585',answer='no'),NOW)
        r=self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein='521273585'),NOW)
        with self.assertRaises(t.Invalid):self.s.submit(self.c,ACCOUNT,self.s.load(self.c,ACCOUNT,r['id']),self.payload(r),NOW+3*86400)
    def test_no_separate_synthetic_create_through_http(self):
        h=Handler(dict(action='create',ein='012345678',name='Example',scenario='open'))
        self.assertEqual(t.handle(self.a,h,origin='https://staging.example')[0],400)
    def test_no_outbound_client_or_submission_endpoint(self):
        tree=ast.parse(Path(t.__file__).read_text())
        imported=[n.names[0].name if isinstance(n,ast.Import) else n.module for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
        self.assertFalse(set(imported)&{'requests','httpx','urllib.request','smtplib','subprocess','socket'})
    def test_generated_application_and_receipt_are_labeled(self):
        from pypdf import PdfReader
        r=self.submit(self.create(),test_response='immediate')
        for url in r['documents'].values():
            row=self.c.execute('SELECT * FROM cc_tn_extension_demo_documents WHERE id=%s',(url.rsplit('/',1)[-1],)).fetchone()
            text=' '.join(x.extract_text() for x in PdfReader(io.BytesIO(row['body'])).pages)
            self.assertIn('DEMO ONLY',text);self.assertIn(r['confirmation'],text);self.assertIn(r['ein'],text)

if __name__=='__main__':unittest.main()
