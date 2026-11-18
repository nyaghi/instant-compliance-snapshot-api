"""Offline document, portal-schema and federal-branch contracts. No live filing."""
import base64,copy,io,json,unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path
from pypdf import PdfReader
from testing.test_tn_extensions_demo import Tests as Base,ACCOUNT,OTHER,NOW
from deployment import tn_extensions_demo as t
from deployment import tn_extension_documents as f
DOCUMENT_CASES=[]
MIGRATION_CASES=[]

class Tests(Base):
    def verified(self,ein='440610626'):
        self.s.dispatch(self.c,ACCOUNT,dict(action='confirm-prior',ein=ein,answer='no'),NOW)
        return self.s.dispatch(self.c,ACCOUNT,dict(action='prepare',ein=ein),NOW)
    def attachment(self,r,kind='8868'):
        d=self.s.dispatch(self.c,ACCOUNT,dict(action='test-document',id=r['id'],kind=kind),NOW)
        raw=self.c.execute('SELECT body FROM cc_tn_extension_demo_documents WHERE id=%s',(d['url'].rsplit('/',1)[-1],)).fetchone()['body']
        return self.s.dispatch(self.c,ACCOUNT,dict(action='upload-support',id=r['id'],body=base64.b64encode(raw).decode()),NOW)
    def federal_values(self,r):
        return r['federal_fields']|dict(books='Demo Books Custodian',phone='816-555-0100',tax_a='0',tax_b='0',tax_c='0')
    def test_70_distinct_document_contracts(self):
        DOCUMENT_CASES.clear();original=t.public_facts
        for i in range(70):
            identifier=str(300000000+i);facts=original('440610626');facts['ein']=identifier;facts['coid']='CO'+str(100000+i);facts['name']='Offline document organization '+str(i)
            patched=patch.object(t,'public_facts',side_effect=lambda e,today=None,identifier=identifier,facts=facts,original=original:copy.deepcopy(facts) if e==identifier else original(e,today));patched.start();self.addCleanup(patched.stop)
            r=self.verified(identifier);mode=i%7
            if mode==0:
                with self.assertRaises(t.Invalid):self.submit(r)
                outcome='missing attachment blocked'
            elif mode==1:
                with self.assertRaises(t.Invalid):self.attachment(r,'mismatch')
                outcome='mismatched EIN blocked'
            elif mode==2:
                with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action='upload-support',id=r['id'],body=base64.b64encode(b'%PDF-unissued').decode()),NOW)
                outcome='unissued document blocked'
            elif mode==3:
                r=self.attachment(r);stored=self.s.load(self.c,ACCOUNT,r['id']);stored['support']['tuple'][3]='2025-08-31';self.s.save(self.c,ACCOUNT,stored,NOW)
                with self.assertRaises(t.Invalid):self.submit(r)
                outcome='wrong period blocked'
            elif mode==4:
                r=self.attachment(r);stored=self.s.load(self.c,ACCOUNT,r['id']);stored['support']['accepted']=False;self.s.save(self.c,ACCOUNT,stored,NOW)
                with self.assertRaises(t.Invalid):self.submit(r)
                outcome='unaccepted federal evidence blocked'
            elif mode==5:
                r=self.attachment(r,'other');d=self.submit(r,test_response='immediate');self.assertEqual(d['status'],'Receipt acknowledged');outcome='other document test receipt, not approval'
            else:
                r=self.attachment(r);d=self.submit(r,test_response='timeout');self.assertEqual(d['state_sends'],1)
                with self.assertRaises(t.Conflict):self.submit(d)
                outcome='timeout duplicate blocked'
            DOCUMENT_CASES.append(dict(ein=r['ein'],mode=mode,outcome=outcome,passed=True));patched.stop()
        self.assertEqual(len(set(x['ein'] for x in DOCUMENT_CASES)),70)
    def test_exact_portal_schema_has_no_paper_fields(self):
        r=self.attachment(self.verified())
        empty=dict.fromkeys(['contact','contact_email','title','reason'],'')
        d=self.submit(r,fields={'coid':r['facts']['coid']}|empty,test_response='immediate')
        self.assertEqual(d['status'],'Receipt acknowledged')
        fields=self.s.fields(d)
        for key in ['Authorized filer','Reason for extension','Days requested','Filer email']:self.assertNotIn(key,fields)
        self.assertIn('Exact attachment SHA256',fields)
    def test_deadline_weekend_and_holiday_and_990n(self):
        self.assertEqual(f.federal_deadline('2026-06-30'),date(2026,11,16))
        self.assertEqual(f.federal_deadline('2026-09-30'),date(2027,2,16))
        facts=t.public_facts('521273585');self.assertFalse(f.federal_status(facts,date(2026,11,18))['eligible'])
        self.assertTrue(f.federal_status(facts,date(2026,11,16))['eligible'])
        facts['return_type']='990-N';self.assertIn('990-N',f.federal_status(facts,date(2026,11,15))['reason'])
        with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action='irs-submit',id=self.verified('521273585')['id']),NOW)
    def test_irs_no_path_prefill_review_acceptance_then_state(self):
        r=self.verified();self.assertFalse(r['federal_found']);self.assertEqual(r['federal_fields']['ein'],'440610626');self.assertEqual(r['federal_fields']['street'],'8701 LEEDS RD')
        p=dict(action='irs-submit',id=r['id'],federal_fields=self.federal_values(r),reviewed=True,authorized=True)
        for change in [dict(reviewed=False),dict(authorized=False),dict(federal_fields=r['federal_fields'])]:
            with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,p|change,NOW)
        d=self.s.dispatch(self.c,ACCOUNT,p,NOW);self.assertTrue(d['support']['accepted']);self.assertEqual(d['irs_submission']['sends'],1)
        repeat=self.s.dispatch(self.c,ACCOUNT,p,NOW);self.assertEqual(repeat['documents'],d['documents'])
        self.assertEqual(self.submit(d,test_response='immediate')['status'],'Receipt acknowledged')
        for kind in ['irs_filed','irs_acceptance']:
            raw=self.c.execute('SELECT body FROM cc_tn_extension_demo_documents WHERE id=%s',(d['documents'][kind].rsplit('/',1)[-1],)).fetchone()['body']
            text=' '.join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages);self.assertIn('DEMO ONLY',text.upper())
    def test_existing_federal_path_scoped_and_period_exact(self):
        first=self.attachment(self.verified());second=self.verified();self.assertTrue(second['federal_found']);self.assertEqual(second['support']['sha256'],first['support']['sha256'])
        other=self.s.create(self.c,OTHER,dict(ein='440610626',name='Other',scenario='open'),NOW)
        self.assertFalse(self.s.find_federal(self.c,OTHER,self.s.load(self.c,OTHER,other['id']),NOW)['federal_found'])
        raw=self.s.load(self.c,ACCOUNT,second['id']);raw['facts']['period_end']='2025-08-31';raw.pop('support');self.s.save(self.c,ACCOUNT,raw,NOW)
        self.assertFalse(self.s.find_federal(self.c,ACCOUNT,raw,NOW)['federal_found'])
    def test_form8868_widget_values_and_watermark(self):
        r=self.verified();data=f.form8868(self.federal_values(r));reader=PdfReader(io.BytesIO(data));fields=reader.get_fields()
        self.assertEqual(len(reader.pages),1)
        values=[v.get('/V') for v in fields.values()]
        for expected in ['440610626','8701 LEEDS RD','01','Demo Books Custodian','0']:self.assertIn(expected,values)
        widgets=[x.get_object() for x in reader.pages[0]['/Annots']]
        self.assertTrue(all('/AP' in x for x in widgets if x.get('/FT')=='/Tx' and x.get('/V')))
        self.assertIn('DEMO ONLY',reader.pages[0].extract_text())
        out=Path(r'C:/Users/nyagh/OneDrive/Desktop/Compliance Express/Projects/CharityClarity/outputs/tn-extension-poc-20261118/RN-FORM8868-PREVIEW.pdf');out.write_bytes(data)
    def test_irs_identity_period_tax_fields_guarded(self):
        r=self.verified();values=self.federal_values(r)
        for changes in [dict(ein='999999999'),dict(period_end='2025-08-31'),dict(return_type='990-PF'),dict(tax_a='10',tax_c='0'),dict(tax_a='NaN'),dict(tax_c='-1'),dict(tax_a='1.123')]:
            with self.assertRaises(ValueError):f.validated_fields(r['facts'],values|changes)
    def test_five_open_candidates_five_closed(self):
        positive=['521273585','680412350','042632526','440610626','042774441']
        all_records=json.loads(Path('deployment/tn-extension-public-references.json').read_text())['records']
        negative=[x['ein'] for x in all_records if x['status']=='Expired'];self.assertEqual(len(negative),5)
        for identifier in positive+negative:
            facts=t.public_facts(identifier);facts['existing_filing']=False
            self.assertEqual(t.eligibility(facts,date(2026,11,18))['eligible'],identifier in positive,identifier)
    def test_resume_old_verified_draft_preserves_data_but_requires_attachment(self):
        r=self.verified();old=self.s.load(self.c,ACCOUNT,r['id']);old.pop('workflow_version');old['fields']['reason']='Keep my original note';self.s.save(self.c,ACCOUNT,old,NOW)
        resumed=self.s.load(self.c,ACCOUNT,r['id']);self.assertEqual(resumed['workflow_version'],2);self.assertEqual(resumed['fields']['reason'],'Keep my original note')
        with self.assertRaises(t.Invalid):self.s.submit(self.c,ACCOUNT,resumed,self.payload(r),NOW)
    def test_70_legacy_draft_migrations_are_bound_and_non_destructive(self):
        MIGRATION_CASES.clear();reference=t.public_facts('521273585')
        for i in range(70):
            ref=copy.deepcopy(reference);identifier=str(400000000+i);ref['ein']=identifier;ref['coid']='CO'+str(400000+i)
            original=copy.deepcopy(ref)
            for key in ['return_type','irs_street','irs_city_state_zip','irs_source']:original.pop(key,None)
            r=dict(ein=identifier,scenario='verified',status='Draft',as_of='2026-11-18',facts=original,fields=dict(reason='Preserve filer wording',name='Keep registered name'))
            case=i%5
            if case==1:r['facts']['coid']='CO1'
            if case==2:r['facts']['period_end']='2025-06-30'
            if case==3:r['status']='Receipt acknowledged'
            if case==4:r['federal_fields']={'books':'Keep my custodian'}
            before=copy.deepcopy(r)
            with patch.object(t,'public_facts',return_value=ref):self.s.upgrade_draft(r)
            enriched=bool(r['facts'].get('return_type'))
            self.assertEqual(enriched,case in [0,4]);self.assertEqual(r['fields'],before['fields'])
            for key,value in before['facts'].items():self.assertEqual(r['facts'][key],value)
            if case==3:self.assertEqual(r,before)
            if case==4:self.assertEqual(r['federal_fields'],before['federal_fields'])
            MIGRATION_CASES.append(dict(ein=identifier,case=case,enriched=enriched,passed=True))
    def test_old_global_draft_gets_deadline_and_8868_packet(self):
        r=self.verified('521273585');old=self.s.load(self.c,ACCOUNT,r['id'])
        for key in ['return_type','irs_street','irs_city_state_zip','irs_source']:old['facts'].pop(key,None)
        old.pop('workflow_version');self.s.save(self.c,ACCOUNT,old,NOW)
        resumed=self.s.load(self.c,ACCOUNT,r['id']);public=self.s.public(resumed)
        self.assertEqual(public['federal_check']['deadline'],'2026-11-16');self.assertIn('deadline has passed',public['federal_check']['reason'])
        self.assertTrue(self.attachment(public)['support']['accepted'])
    def test_http_upload_boundaries_and_real_docs_rejected(self):
        r=self.verified()
        for body in ['!!!!',base64.b64encode(b'not PDF').decode(),base64.b64encode(b'%PDF'+b'x'*2097152).decode()]:
            with self.assertRaises(t.Invalid):self.s.dispatch(self.c,ACCOUNT,dict(action='upload-support',id=r['id'],body=body),NOW)

if __name__=='__main__':unittest.main()
