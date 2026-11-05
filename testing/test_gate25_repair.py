"""Observed Gate25 fixtures through master selection and original-PDF binding."""
import base64, copy, hashlib, json, socket, tempfile, time, unittest
from pathlib import Path
from datetime import date
from unittest.mock import Mock, patch
import registry_snapshot_server as m
from deployment import state_snapshots as ss, dc_linked_identity as dc, dc_boss_evidence as boss
from deployment import desktop_source_evidence as desktop
from testing.test_state_snapshots import image
from testing.run_wv_sc_selection_guardrails import SelectionTests
from pypdf import PdfReader
import io
F=Path(__file__).parent/'fixtures/gate25'

class Repairs(unittest.TestCase):
    def setUp(self):
        p=patch.object(socket,'create_connection',side_effect=AssertionError('No live source calls in local replay'))
        p.start();self.addCleanup(p.stop)

    def test_il_observed_missing_fein_parser_selection_and_snapshot(self):
        body=(F/'il-wnet.txt').read_text(encoding='utf-8').split('\nDetails\n',1)[1]
        org=m.checker.Organization('WNET','262810489')
        parsed=m.il_charity_detail_text(body,'01100573');self.assertEqual(parsed['ein'],'')
        address=dict(ein=org.ein,street='825 EIGHTH AVENUE 14TH FL',city='NEW YORK',state='NY',postal_code='100197435',address_role='organization')
        row=dict(name='WNET',identifier='01100573',street='825 EIGHTH AVENUE, 14TH/F',region='NY',postal_code='10019',location='NEW YORK, NY 10019')
        def evidence(q):
            if 'identifier' in q:return {'body':body}
            return {'rows':[] if 'ein' in q else [row]}
        with patch.object(m,'known_names_for_ein',return_value=[]),patch.object(m,'licensed_charity_names',return_value=(['WNET'],[])), \
                patch.object(m,'IDENTITY_SOURCE_CACHE',{}),patch.object(m,'identity_source_result',return_value={'source':'IRS','address':address}):
            result=m.il_ga_browser_lookup(org,'IL',evidence)
            self.assertTrue(result.success);self.assertEqual(result.matched_registry_identifier,'01100573')
            self.assertEqual(result.status,'Upcoming Filing');self.assertIn('omits FEIN',result.source_note)
            self.assertEqual(ss.il_selected_detail_snapshot({'identifier':'01100573'},{'body':body},m.IL_GA_SOURCES['IL'],body,org.ein),('01100573','WNET'))
            for changed in [dict(row,street='999 DIFFERENT AVENUE'),dict(row,postal_code='10020'),dict(row,region='CA')]:
                self.assertEqual(m.licensed_charity_identity(org,{**changed,**parsed},'IL',time.monotonic()+6),'possible')
        for value in ['123456789','bad']:
            changed=body+'\nFEIN: '+value
            self.assertIsNone(ss.il_selected_detail_snapshot({'identifier':'01100573'},{'body':changed},m.IL_GA_SOURCES['IL'],changed,org.ein))
        for changed in [body.replace('01100573','01100574'),body+'\nCO Number: 01100573']:
            with self.assertRaises(ValueError):m.il_charity_detail_text(changed,'01100573')
        self.assertIsNone(ss.il_selected_detail_snapshot({'identifier':'01100573'},{'body':body},m.IL_GA_SOURCES['IL'],body+'\nFEIN: 123456789',org.ein))

    def test_ca_actual_completed_empty_shell_and_failed_detail(self):
        fixture=json.loads((F/'ca-apmg.json').read_text(encoding='utf-8'))[0]
        org=m.checker.Organization('American Public Media Group','363503764')
        def fresh():
            r=m.checker.StateResult(org.organization_name,org.ein,'CA',m.checker.STATUS_NOT_REGISTERED,'https://ca-rcf.evokeplatform.com/')
            r.success=True;return r
        with patch.object(m,'trial_identity',return_value=True),patch.object(m.checker,'search_ca',side_effect=lambda *_:fresh()), \
                patch.object(m.checker,'ca_evoke_entity_search_by_name',return_value=[fixture['entity']]), \
                patch.object(m,'ca_master_name_identity',return_value='possible'), \
                patch.object(m.checker,'ca_evoke_registrations_for_entity',return_value=[]) as get:
            r=m.search_ca_master(None,org);self.assertTrue(r.success);self.assertEqual(r.status,m.checker.STATUS_NOT_REGISTERED)
            self.assertFalse(r.matched_registry_identifier);self.assertIn('empty',r.source_note)
            for value in [None,{},[{}]]:
                get.return_value=value;r=m.search_ca_master(None,org);self.assertFalse(r.success)
            get.side_effect=TimeoutError('modeled source failure');r=m.search_ca_master(None,org);self.assertFalse(r.success)

    def test_ma_explicit_deactivated_keeps_confirmed_record(self):
        org=m.checker.Organization('National Book Foundation Inc.','133347524')
        def result():
            r=m.checker.StateResult(org.organization_name,org.ein,'MA','Delinquent','https://masscharities.my.site.com/')
            r.success=True;r.matched_registry_name=org.organization_name;r.matched_registry_identifier='034900';return r
        r=result();m.annotate_ma_visible_form_pc_due(r,dict(ago_account='034900',registry_status='Deactivated',contrary_status=True))
        m.normalize_registry_match_fields(r,org)
        self.assertEqual(r.status,'Closed / Withdrawn / Canceled');self.assertEqual(r.matched_registry_identifier,'034900')
        self.assertEqual(r.raw_status_text,'Charity Status: Deactivated')
        from deployment import ma_view_more_evidence as ma
        run=ss.CaptureRun(org.organization_name,org.ein,'MA')
        text=org.organization_name+'\nAG Account Number: 034900\nEIN 13-3347524\nCharity Status: Deactivated'
        raw=image('LOCAL MA FIXTURE',text)
        url='https://masscharities.my.site.com/FilingSearch/s/'
        run.document(url,raw,'image',text)
        run.ma_view_more_bindings={hashlib.sha256(raw).hexdigest():dict(role='main',url=url,record=dict(ago_account='034900',name=org.organization_name,ein=org.ein))}
        row={**vars(r),'state':'MA','ein':org.ein,'organization_name':org.organization_name}
        self.assertEqual(len(ma.select(run,run.documents,row)),1)
        self.assertTrue(run.finish(row).get('_worker_source_archives'))
        self.assertEqual(ma.select(run,run.documents,{**row,'matched_registry_identifier':'999999'}),[])
        for ago,standing in [('999999','Deactivated'),('034900','Suspended'),('034900','Unknown')]:
            r=result();m.annotate_ma_visible_form_pc_due(r,dict(ago_account=ago,registry_status=standing,contrary_status=True))
            self.assertNotEqual(r.status,'Closed / Withdrawn / Canceled')

class WestVirginia(SelectionTests):
    def test_retrieval_fragment_cannot_promote_unrelated_public_media(self):
        self.assertFalse(m.registry_name_is_safe_against_targets('Public Media Group of Southern California',m.organization_match_target_variants('American Public Media Group','363503764'),'American Public Media Group','363503764'))
        result,selected=self.wv([('1349','Public Media Group of Southern California','Expired')],name='American Public Media Group')
        self.assertFalse(selected);self.assertFalse(result.matched_registry_identifier)
        source=Mock();source.search.return_value=('Search results',[dict(index=0,count=5,values=['1349','Public Media Group of Southern California','Expired'],target='fixture')])
        plan=['American Public Media Group','public media group']
        with patch.object(m,'wv_preferred_query_variants',return_value=plan),patch.object(m,'wv_core_search_completed',return_value=True):
            result=m.search_wv_precise(None,m.checker.Organization('American Public Media Group','363503764'),public_lookup=source)
        self.assertEqual(result.status,m.checker.STATUS_NOT_REGISTERED);source.detail.assert_not_called()
        self.assertEqual([v.args[0] for v in source.search.call_args_list],plan)

class LinkedDC(unittest.TestCase):
    def test_candidate_uses_retained_ein_office_and_requires_one_specific_short_name(self):
        from urllib.parse import urlencode
        org=m.checker.Organization('Sundance Institute','870361394')
        old=dict(name=org.organization_name,status='Delinquent',expiration=date(2020,2,29),_identity_outcome='accepted')
        current=dict(name='SUNDANCE',identifier='400222000224',status='Current',raw_status='Active',expiration=date(2028,2,28),license_category='Charitable Solicitation',url=m.DC_LICENSE_API+'?'+urlencode(dict(where="CUSTOMERNUMBER='400222000224'",outFields='*',returnGeometry='false',f='pjson')))
        profile=dict(organization=dict(ein=870361394,street='PO BOX 684429',city='Park City',state='UT',zipcode='84068'))
        with patch.object(m,'known_names_for_ein',return_value=[]),patch.object(m,'IDENTITY_SOURCE_CACHE',{}),patch.object(m,'PUBLIC_PROFILE_CACHE',{org.ein:profile}):
            self.assertIsNotNone(dc.candidate(m,org,old,[old,current]))
            for rows in [[old,current,dict(current)],[old,dict(current,name='Other')],[old,dict(current,match={'reason':'USER_REJECTED_IDENTITY'})],[old,dict(current,expiration=date(2019,1,1))]]:
                self.assertIsNone(dc.candidate(m,org,old,rows))
        with patch.object(m,'IDENTITY_SOURCE_CACHE',{}),patch.object(m,'PUBLIC_PROFILE_CACHE',{}):
            self.assertIsNone(dc.candidate(m,org,old,[old,current]))

    def setUp(self):
        now=time.time(); self.q=dict(state='DC',operation='detail',url=boss.SEARCH,ein='870361394',run_id='a'*32,
            deadline_schema=1,issued_at=now-1,expires_at=now+120,name='SUNDANCE INSTITUTE',identifier='400212000168',
            raw_status='Expired - Enforcement',expiration='2020-02-29',result_raw_status='Expired - Enforcement',corporate_continuity_schema=2,
            corporate_continuity_candidate=dict(identifier='400222000224',name='SUNDANCE',raw_status='Active',expiration='2028-02-28'),
            corporate_link_proof=dict(names=['Sundance Institute'],addresses=[dict(street='P.O. BOX 684429',region='UT',postal='84068')]))
        self.r=dict(state='DC',organization_name='Sundance Institute',ein=self.q['ein'],status='Delinquent',success=True,matched_registry_identifier=self.q['identifier'],matched_registry_name=self.q['name'],raw_status_text=self.q['raw_status'],_worker_desktop_evidence=self.q)
        target=dc.request_for_candidate(self.q);text=(F/'dc-license.txt').read_text(encoding='utf-8');url='https://boss.dc.gov/licensing/license-details'
        self.current=dict(request=target,url=url,public_text=text,source_fields=boss.fields(url,text,target),captured_at=now,image=base64.b64encode(image('LOCAL LICENSE FIXTURE','400222000224')).decode())
        self.corporate=dict(url=dc.CORPORATE_URL,public_text=(F/'dc-corporate.txt').read_text(encoding='utf-8'),linked_identifier='N0000001384',captured_at=now,image=base64.b64encode(image('LOCAL CORPORATE FIXTURE','N0000001384')).decode())
        self.p=dict(request=self.q,current_license=self.current,corporate_detail=self.corporate)

    def test_observed_linked_identity_archives_both_originals_atomically(self):
        self.assertIsNotNone(self.current['source_fields']);dc.validate(self.r,self.p)
        with tempfile.TemporaryDirectory() as directory:
            store=ss.SQLiteStore(Path(directory)/'snapshots.sqlite')
            update=desktop.persist_completion(self.r,self.p,store)
            self.assertEqual(update['status'],'Current');self.assertEqual(update['matched_registry_identifier'],'400222000224')
            row=ss.saved_pdf(update['evidence_url'].rsplit('/',1)[-1].split('.')[0],store);self.assertIsNotNone(row)
            self.assertEqual(len(PdfReader(io.BytesIO(row[1])).pages),2)
        self.assertEqual(self.r['status'],'Delinquent')

    def test_wrong_corporate_link_name_address_license_and_stale_capture_rejected(self):
        for old,new in [('N0000001384','N0000001385'),('SUNDANCE INSTITUTE','OTHER INSTITUTE'),('PO Box 684429','PO Box 999999'),('1500 Kearns','1501 Kearns')]:
            p=copy.deepcopy(self.p);p['corporate_detail']['public_text']=p['corporate_detail']['public_text'].replace(old,new)
            with self.assertRaises(ValueError):dc.validate(self.r,p)
        for item,key,value in [('current_license','captured_at',self.q['expires_at']+1),('corporate_detail','image',''),('corporate_detail','url','https://other.example/')]:
            p=copy.deepcopy(self.p);p[item][key]=value
            with self.assertRaises(ValueError):dc.validate(self.r,p)
        p=copy.deepcopy(self.p);p['current_license']['source_fields']['License Number']='999999999999'
        with self.assertRaises(ValueError):dc.validate(self.r,p)

if __name__=='__main__':unittest.main(verbosity=2)
