import copy,json,time,unittest
from pathlib import Path
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
import registry_snapshot_server as m
from deployment import dc_boss_evidence as b,dc_corporate_continuity as c,dc_period_reconciliation as period

class Binding(unittest.TestCase):
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
