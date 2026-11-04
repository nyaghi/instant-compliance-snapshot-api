import copy,json,time,unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
import registry_snapshot_server as m
from deployment import dc_boss_evidence as b,dc_corporate_continuity as c,dc_period_reconciliation as period

class Binding(unittest.TestCase):
    def test_actual_frontend_merges_continuity_status_and_evidence_together(self):
        import subprocess
        root=Path(__file__).resolve().parents[1]
        before={**self.r,'desktop_evidence_request':self.q}
        after={**period.public_completed_fields({**self.r,**c.update(self.r,self.p)}),
            'evidence_capture':'captured','evidence_url':'/state-snapshots/'+'a'*64+'.pdf',
            'evidence_captured_at':self.p['current_license']['captured_at']}
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('web-staging/optimized-workflows.js','utf8');
const code=source.slice(source.indexOf('    const dcPeriodKeys='),source.indexOf('    async function captureOriginal('));
const x=JSON.parse(fs.readFileSync(0,'utf8')),ctx={};vm.createContext(ctx);
vm.runInContext(code+';this.apply=applySavedEvidence;',ctx);
const clone=x=>JSON.parse(JSON.stringify(x));
let b=clone(x.before);assert.equal(ctx.apply(b,x.after),true);
for(const k of ['status','comments','computed_due_date','matched_registry_identifier','matched_registry_name','raw_status_text','renewal_date','renewal_filing_value','evidence_url'])assert.equal(b[k],x.after[k],k);
const changes=[['ein','111111111'],['run_id','b'.repeat(32)],['prior_identifier','99999'],['prior_name','OTHER'],['prior_status','Current'],['prior_expiration','2000-01-01'],['identifier','99999'],['name','OTHER'],['expiration','2000-01-01'],['raw_status','Closed'],['status','Delinquent'],['issue_date','bad'],['corporate_record',''],['source_url','https://other.example'],['captured_at',0]];
for(const [k,v] of changes){let a=clone(x.after);a.dc_source_reconciliation[k]=v;b=clone(x.before);assert.equal(ctx.apply(b,a),false,k);assert.deepEqual(b,x.before,k);}
for(const [k,v] of [['evidence_capture','failed'],['matched_registry_identifier','99999'],['status','Delinquent'],['confirmation_required',true],['renewal_filing_value','2000-01-01']]){let a=clone(x.after);a[k]=v;b=clone(x.before);assert.equal(ctx.apply(b,a),false,k);assert.deepEqual(b,x.before,k);}
// Legacy evidence-only responses still attach without changing a status.
b={state:'DC',status:'Current',desktop_evidence_request:{}};assert.equal(ctx.apply(b,{evidence_url:x.after.evidence_url,status:'Delinquent'}),true);assert.equal(b.status,'Current');
(async()=>{
for(const lost of [false,true]){
 const listeners=new Set();let polls=0,archives=0;
 const window={addEventListener:(k,f)=>listeners.add(f),removeEventListener:(k,f)=>listeners.delete(f),postMessage(m){queueMicrotask(()=>{for(const f of [...listeners])f({source:window,origin:'https://staging.compliance-express.com',data:{...m,direction:'response',result:{ok:true}}});});}};
 const context={window,location:{origin:'https://staging.compliance-express.com'},crypto:require('crypto').webcrypto,AbortSignal,performance,Date,setTimeout,clearTimeout,
 fetch:async(url,options)=>{const d=JSON.parse(options.body);if(url.endsWith('/api/source-evidence')){archives++;if(lost)throw new TypeError('modeled lost acknowledgement');return {ok:true,json:async()=>clone(x.after)};}
 if(d.action==='start')return {ok:true,json:async()=>({token:'same-workflow'})};
 if(d.action==='poll'){polls++;return {ok:true,json:async()=>({results:[polls===1?clone(x.before):{...clone(x.before),...clone(x.after)}],finished:1})};}
 return {ok:true,json:async()=>({ok:true})};}};
 vm.createContext(context);vm.runInContext(source,context);
 const [result]=await window.CCOptimized.run({apiBase:'https://fixture.invalid',name:'Management Sciences for Health',ein:x.before.ein,states:['DC'],credentials:{}});
 for(const k of ['status','matched_registry_identifier','matched_registry_name','raw_status_text','renewal_filing_value','evidence_url'])assert.equal(result[k],x.after[k],k+':'+lost);
 assert.equal(archives,1);
}
console.log('20 continuity rejection cases, legacy control, full transport normal/lost acknowledgment passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',script],cwd=root,input=json.dumps(dict(before=before,after=after)),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_dc_archive_and_status_change_are_atomic(self):
        import base64,io,tempfile
        from PIL import Image,ImageDraw
        from deployment import state_snapshots as s,desktop_source_evidence as desktop
        image=Image.new('RGB',(800,600),'white');ImageDraw.Draw(image).text((20,20),'LOCAL MODELED ORIGINAL IMAGE',fill='black')
        data=io.BytesIO();image.save(data,format='PNG')
        payload=copy.deepcopy(self.p)
        for key in ['prior_license','current_license']:payload[key]['image']=base64.b64encode(data.getvalue()).decode()
        with tempfile.TemporaryDirectory() as directory:
            store=s.SQLiteStore(Path(directory)/'evidence.db')
            update=desktop.persist_completion(self.r,payload,store)
            self.assertEqual(update['matched_registry_identifier'],'400225000492')
            self.assertEqual(update['status'],'Current')
            ident=update['evidence_url'].split('/')[-1].split('.')[0]
            meta,pdf=s.saved_pdf(ident,store)
            self.assertEqual(meta['identifier'],'400225000492');self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertEqual(self.r['status'],'Delinquent')
        from unittest.mock import Mock
        store=Mock();store.save.side_effect=RuntimeError('modeled archive failure')
        with self.assertRaises(RuntimeError):desktop.persist_completion(self.r,payload,store)
        self.assertEqual(self.r['matched_registry_identifier'],'400219000523')

    def setUp(self):
        now=time.time();self.q=dict(state='DC',operation='detail',url=b.SEARCH,ein='042482188',run_id='a'*32,
            deadline_schema=1,issued_at=now,expires_at=now+120,name='MANAGEMENT SCIENCES FOR HEALTH',identifier='400219000523',
            raw_status='Expired - Enforcement',expiration='2025-06-30',result_raw_status='Expired - Enforcement',
            corporate_continuity_schema=1,corporate_continuity_candidate=dict(identifier='400225000492',name='MANAGEMENT SCIENCES FOR HEALTH',raw_status='Active',expiration='2027-08-31'))
        self.r=dict(state='DC',ein='042482188',status='Delinquent',success=True,matched_registry_identifier=self.q['identifier'],
            matched_registry_name=self.q['name'],raw_status_text=self.q['raw_status'],_worker_desktop_evidence=self.q)
        def payload(q,file):
            text=(Path(__file__).parent/'fixtures'/file).read_text(encoding='utf-8')
            fields=b.fields('https://boss.dc.gov/licensing/license-details',text,q)
            self.assertIsNotNone(fields)
            return dict(request=copy.deepcopy(q),url='https://boss.dc.gov/licensing/license-details',public_text=text,
                source_fields=fields,captured_at=now,image='original-image-placeholder')
        self.old=payload(self.q,'DC-MSH-prior.txt');self.new=payload(c.request_for_candidate(self.q),'DC-MSH-current.txt')
        self.p={**self.new,'request':self.q,'prior_license':self.old,'current_license':self.new}

    def test_actual_two_licenses_require_same_corporate_identity(self):
        self.assertEqual(c.validate(self.r,self.p)[3],'N0000000163')
        update=period.completed_update(self.r,self.p)
        self.assertEqual(update['status'],'Current');self.assertEqual(update['matched_registry_identifier'],'400225000492')
        self.assertEqual(period.public_completed_fields({**self.r,**update})['matched_registry_identifier'],'400225000492')
        for old,new in [('N0000000163','N0000000164'),('MANAGEMENT SCIENCES FOR HEALTH','OTHER HEALTH ENTITY')]:
            p=copy.deepcopy(self.p);p['current_license']['public_text']=p['current_license']['public_text'].replace(old,new)
            with self.assertRaises(ValueError):c.validate(self.r,p)
        for key,value in [('image',''),('captured_at',self.q['expires_at']+1),('url','https://other.example/')]:
            p=copy.deepcopy(self.p);p['current_license'][key]=value
            with self.assertRaises(ValueError):c.validate(self.r,p)

    def test_candidate_requires_old_address_proof_unique_newer_record(self):
        old=dict(name=self.q['name'],status='Delinquent',expiration=date(2025,6,30),_identity_outcome='accepted',address_evidence={'decision':'corroborated'})
        new=dict(name=self.q['name'],identifier='400225000492',status='Current',raw_status='Active',expiration=date(2027,8,31),_identity_outcome='conflict',license_category='Charitable Solicitation',url="https://maps2.dcgis.dc.gov/dcgis/rest/services/FEEDS/DCRA/FeatureServer/0/query?where=CUSTOMERNUMBER%3D%27400225000492%27&outFields=*&returnGeometry=false&f=pjson")
        self.assertIsNotNone(c.candidate(old,[old,new]))
        for changed in [dict(new,name='OTHER'),dict(new,expiration=date(2024,1,1)),dict(new,match={'reason':'REJECT_DIFFERENT_EIN'})]:
            self.assertIsNone(c.candidate(old,[old,changed]))
        self.assertIsNone(c.candidate(old,[old,new,dict(new)]))
        self.assertIsNone(c.candidate({**old,'expiration':None},[new]))

    def test_wa_completed_name_response_excludes_wrong_ein_but_never_incomplete(self):
        wa=m.load_wa_nm_module()
        row=dict(EntityName='Child Family Health International',FEINNumber='94-3145385',Criteria={'TotalRowCount':1},TotalPageCount=1)
        tracker=dict(completed=True,pending=False,failed=False,lastStatus=200,lastText=json.dumps([row]))
        self.assertEqual(wa.wa_name_response_identity(tracker,'237413005'),'NO_VALUE')
        self.assertEqual(wa.wa_name_response_identity(tracker,'943145385'),row)
        for field,value in [('pending',True),('completed',False),('failed',True),('lastStatus',503),('lastText','{')]:
            self.assertIsNone(wa.wa_name_response_identity({**tracker,field:value},'237413005'))
        for changed in [dict(row,FEINNumber=''),dict(row,TotalPageCount=2),dict(row,Criteria={'TotalRowCount':100})]:
            self.assertIsNone(wa.wa_name_response_identity({**tracker,'lastText':json.dumps([changed])},'237413005'))

    def test_or_extract_binds_exact_record_and_preserves_periods(self):
        from deployment import or_export_evidence as o
        url='https://justice.oregon.gov/Charities/Charity/details?charityID=9995'
        value=o.extract('362586390','MAP International, Inc.','Fiscal Year Beginning 10/01/2023 Ending 09/30/2024',url)
        self.assertEqual(value['row']['PeriodEnding'],'09/30/2025')
        self.assertEqual(value['portal_periods'],[['10/01/2023','09/30/2024']])
        self.assertIsNone(o.extract('362586390','Other Foundation','',url))
        self.assertIsNone(o.extract('362586390','MAP International, Inc.','',url+'1'))
        o.validate(value,dict(state='OR',ein='362586390',source_url=url))
        with self.assertRaises(ValueError):o.validate(value,dict(state='OR',ein='111111111',source_url=url))

if __name__=='__main__':unittest.main()
