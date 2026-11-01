"""Same-license renewal requires stable original pixels and atomic interpretation."""
import base64,copy,io,json,os,tempfile,time,unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image,ImageDraw
import registry_snapshot_server as m
from deployment import dc_boss_evidence as b,dc_period_reconciliation as p,desktop_source_evidence as d,state_snapshots as s
F=json.loads((Path(__file__).parent/'fixtures/dc-erm-period.json').read_text())
class AsOf(date):
    @classmethod
    def today(cls):return date(2026,10,31)
def text(fields):return 'License Information\n'+'\n'.join(k+'\n'+fields[k]for k in b.LABELS)+'\nLicensee Information\n'

class PeriodReconciliation(unittest.TestCase):
    def setUp(self):
        self.result=copy.deepcopy(F['result']);self.fields=copy.deepcopy(F['fields'])
        self.run=SimpleNamespace(state='DC',ein='232792333',run_id='a'*32,
          dc_boss_selected={'identifier':'400215000055','name':self.result['matched_registry_name'],'raw_status':'Active','expiration':'2026-10-31'},dc_boss_selected_activity='Charitable Solicitation')
        q=patch.object(m,'trial_identity',return_value={'origin':'local'});q.start();self.addCleanup(q.stop)
        q=patch.object(m,'date',AsOf);q.start();self.addCleanup(q.stop)
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('standard');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)
        self.request=b.retained_request(self.run,self.result);self.result['_worker_desktop_evidence']=self.request
        out=io.BytesIO();image=Image.new('RGB',(800,600),'white')
        ImageDraw.Draw(image).text((20,20),'LOCAL MODELED FIXTURE\n'+text(self.fields),fill='black');image.save(out,format='PNG')
        self.payload={'request':copy.deepcopy(self.request),'url':'https://boss.dc.gov/licensing/license-details',
          'public_text':text(self.fields),'source_fields':copy.deepcopy(self.fields),'captured_at':self.request['issued_at']+.001,
          'image':base64.b64encode(out.getvalue()).decode()}
    def test_saved_erm_period_is_reconciled_without_changing_identity_or_initial_date(self):
        self.assertEqual(self.request['boss_reconcile_schema'],1);original=copy.deepcopy(self.result)
        update=p.completed_update(self.result,self.payload)
        self.assertEqual(update['status'],'Current');self.assertEqual(update['computed_due_date'],'2028-10-31')
        self.assertEqual(update['renewal_date'],'2026-10-30');self.assertEqual(update['renewal_date_source_label'],'Issue Date')
        self.assertNotIn('registration_date',update);self.assertNotIn('matched_registry_name',update)
        self.assertIn('2026-10-31',update['comments']);self.assertIn('2028-10-31',update['comments'])
        self.assertEqual(self.result,original);self.assertNotIn('evidence_url',update)
    def test_existing_display_projection_is_recomputed_with_the_source_period(self):
        # The original fixture omitted these five fields present in the public
        # result. They take precedence over renewal_date in the real UI/export.
        self.assertEqual(self.result['renewal_filing_value'],'2024-11-01')
        update=p.completed_update(self.result,self.payload)
        self.assertEqual(update['renewal_filing_value'],'2026-10-30')
        self.assertEqual(update['renewal_filing_type'],'current_issue_date')
        self.assertEqual(update['renewal_filing_label'],'Current registration issued')
        self.assertEqual(update['renewal_filing_source_url'],self.payload['url'])
        self.assertEqual(update['renewal_filing_note'],update['renewal_date_note'])
        self.assertEqual(p.public_completed_fields({**self.result,**update})['renewal_filing_value'],'2026-10-30')
    def test_period_and_evidence_share_one_persisted_update_and_failed_archive_changes_nothing(self):
        original=copy.deepcopy(self.result)
        with tempfile.TemporaryDirectory()as folder:
            store=s.SQLiteStore(str(Path(folder)/'source.db'));update=d.persist_completion(self.result,self.payload,store)
            self.assertEqual(update['status'],'Current');self.assertEqual(update['evidence_capture'],'captured')
            ident=update['evidence_url'].split('/')[-1].split('.')[0];meta,pdf=s.saved_pdf(ident,store)
            self.assertTrue(pdf.startswith(b'%PDF'));self.assertEqual(meta['identifier'],'400215000055')
        self.assertEqual(self.result,original)
        store=Mock();store.save.side_effect=RuntimeError('modeled archive failure')
        with self.assertRaises(RuntimeError):d.persist_completion(self.result,self.payload,store)
        self.assertEqual(self.result,original)
    def test_wrong_identity_activity_standing_date_url_or_challenge_cannot_update(self):
        variants=[('License Number','999999999999'),('Licensee','Different Foundation'),('License Activity','Charitable Exempt'),('License Status','Revoked'),('Expiration Date','10/31/2025'),('Expiration Date','02/30/2028'),('Issue Date','10/30/2030'),('Issue Date','11/01/2024')]
        for key,value in variants:
            with self.subTest(key=key,value=value):
                f={**self.fields,key:value};payload={**self.payload,'source_fields':f,'public_text':text(f)}
                with self.assertRaises(ValueError):d.validate_completion(self.result,payload)
        for payload in [{**self.payload,'url':'https://other.example/detail'},{**self.payload,'public_text':'Verify you are human\n'+text(self.fields)},{**self.payload,'captured_at':self.request['expires_at']+1}]:
            with self.assertRaises(ValueError):d.validate_completion(self.result,payload)
    def test_stale_request_schema_status_comment_or_review_decision_cannot_be_reused(self):
        for key,value in [('status','Delinquent'),('renewal_date','2024-10-31'),('comments','Changed comments')]:
            with self.subTest(key=key):self.assertIsNone(b.describe({**self.result,key:value}))
        for change in [{'boss_reconcile_schema':True},{'boss_reconcile_schema':2},{'review_candidate':True},{'prior_renewal_date':'bad'},{'expected_activity':'other'}]:
            result={**self.result,'_worker_desktop_evidence':{**self.request,**change}}
            self.assertIsNone(b.describe(result))
        self.assertIsNone(b.describe({**self.result,'_worker_identity_review':{'records':[{}]}}))
    def test_nontrial_sales_uncorroborated_and_unresolved_records_keep_legacy_period_binding(self):
        with patch.object(m,'trial_identity',return_value=None):self.assertNotIn('boss_reconcile_schema',b.retained_request(self.run,self.result))
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales')
        try:self.assertNotIn('boss_reconcile_schema',b.retained_request(self.run,self.result))
        finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)
        self.assertNotIn('boss_reconcile_schema',b.retained_request(self.run,{**self.result,'address_evidence':{'decision':'unavailable'}}))
        old={k:v for k,v in self.request.items()if k not in {'boss_reconcile_schema','expected_activity','prior_status','prior_renewal_date','prior_comments_sha256'}}
        self.assertIsNone(b.fields(self.payload['url'],text(self.fields),old))
        legacy={**self.fields,'Licensee':old['name'],'Expiration Date':'10/31/2026'}
        self.assertEqual(b.fields(self.payload['url'],text(legacy),old),legacy)
    def test_thirty_names_allow_only_article_movement_with_the_same_exact_license(self):
        for i in range(30):
            name='Example Foundation '+str(i);request={**self.request,'name':name}
            for observed in [name,'THE '+name,name+' (THE)']:
                self.assertTrue(p.name_matches(observed,name,request))
            for observed in [name+' of Texas',name+' THE','THEORY '+name,'THE '+name+' (THE)','Unrelated']:
                self.assertFalse(p.name_matches(observed,name,request))
            self.assertFalse(p.name_matches('THE '+name,name,{}))
    def test_duplicate_acknowledgement_contains_the_same_complete_period(self):
        update=p.completed_update(self.result,self.payload);settled={**self.result,**update}
        public=p.public_completed_fields(settled)
        self.assertEqual(public['status'],'Current');self.assertEqual(public['comments'],update['comments'])
        self.assertEqual(public['renewal_date'],'2026-10-30');self.assertEqual(public['dc_source_reconciliation'],update['dc_source_reconciliation'])
        self.assertEqual(public['renewal_filing_value'],'2026-10-30')
        self.assertEqual(public['renewal_filing_label'],'Current registration issued')
        self.assertEqual(p.public_completed_fields(self.result),{})
    def test_actual_public_poll_projection_retains_the_new_period_and_source_together(self):
        from deployment.staging_workflows import public_result
        with tempfile.TemporaryDirectory()as folder:
            store=s.SQLiteStore(str(Path(folder)/'source.db'));update=d.persist_completion(self.result,self.payload,store)
            settled={**self.result,**update};version=settled['app_version']
            with patch.dict(os.environ,{'CE_STAGING_WORKFLOW_VERSION':version}):
                public=public_result(m,{'phase':'done','state':'DC','result':settled},{'ein':self.run.ein,'states':['DC']})
            self.assertEqual(public['status'],'Current');self.assertEqual(public['comments'],update['comments'])
            self.assertEqual(public['renewal_date'],'2026-10-30');self.assertEqual(public['evidence_url'],update['evidence_url'])
            self.assertEqual(public['renewal_filing_value'],'2026-10-30')
            self.assertEqual(public['renewal_filing_label'],'Current registration issued')
            self.assertFalse(public['confirmation_required']);self.assertNotIn('desktop_evidence_request',public)
            self.assertEqual(public['registration_date'],self.result['registration_date'])

if __name__=='__main__':unittest.main()
