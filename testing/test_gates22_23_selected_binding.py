"""Selected public-record status, capture hints and archive identity joined locally."""
import copy,time,unittest
import json
from pathlib import Path
from unittest.mock import Mock,patch
import registry_snapshot_server as m
from deployment import source_visual_adapters as v,state_snapshots as s
from testing.test_gates22_23_capture_budget import fixture_image,CaptureBinding

class SelectedBinding(unittest.TestCase):
    persist=CaptureBinding.persist

    def test_ca_identity_conflict_is_not_reported_as_site_unreachable(self):
        org=m.checker.Organization('Example Center','123456789')
        original=m.checker.StateResult(org.organization_name,org.ein,'CA',m.checker.STATUS_NOT_REGISTERED,'https://ca-rcf.evokeplatform.com/')
        original.success=True
        foreign={'id':'12345','entityName':org.organization_name,'fein':'987654321','entityStatus':'Exempt'}
        with patch.object(m,'trial_identity',return_value=False),patch.object(m.checker,'search_ca',return_value=original), \
             patch.object(m.checker,'ca_evoke_entity_search_by_name',return_value=[foreign]):
            result=m.search_ca_master(Mock(),org)
        self.assertEqual(result.status,'Unable to Confirm');self.assertFalse(result.success)
        self.assertIn('conflicts',result.error)

    def test_nv_observed_compound_row_reaches_csr_status_and_original_archive(self):
        data=json.loads((Path(__file__).parent/'fixtures/gates22-23/nv-guggenheim.json').read_text(encoding='utf-8'))
        org=m.checker.Organization(data['requested_name'],data['requested_ein'])
        fields=data['fields'];run=s.CaptureRun(org.organization_name,org.ein,'NV');calls=[]
        # The search grid exposes an empty type; '-' is the detail display.
        search_row={'name':fields['Entity Name'],'identifier':fields['NV Business ID'],
                    'entity_type':'','entity_number':fields['Entity Number'],'raw_status':'Expired'}
        def provider(query):
            calls.append(query)
            if query['operation']=='search':
                return {'state':'NV','query':query,'complete':True,'verification_pending':False,'total':1,'rows':[search_row]}
            return {'query':query,'complete':True,'fields':copy.deepcopy(fields),'filings':copy.deepcopy(data['history']),'source_url':data['source_url']}
        token=m.REVIEWED_NAME_CONTEXT.set({org.ein:data['aliases']})
        self.addCleanup(m.REVIEWED_NAME_CONTEXT.reset,token)
        with patch.object(m,'trial_identity',return_value=True), \
             patch.object(m,'reconciled_registry_address',return_value={'decision':'not_available'}), \
             patch.object(m,'licensed_charity_foreign_ein',return_value={}),patch.object(m,'licensed_charity_street_evidence',return_value={}):
            result=m.final_four_browser_lookup(org,'NV',provider)
            self.assertEqual(result.status,'Delinquent',(result.source_note,result.error,calls));self.assertTrue(result.success)
            self.assertEqual(result.matched_registry_identifier,fields['NV Business ID'])
            self.assertEqual(sum(q['operation']=='detail' for q in calls),1)
            public=m.response_data_for_lookup(result,result.raw_status_text,org,run.name,run.ein,'NV',time.perf_counter())
            self.assertEqual(public['matched_registry_name'],fields['Entity Name'])
            text='\n'.join(k+' '+v for k,v in fields.items())
            run.document(data['source_url'],fixture_image(text),'image',text)
            self.persist(run,public)

    def test_oh_parent_filing_original_and_explanation_survive_export(self):
        from deployment import oh_detail_evidence
        org=m.checker.Organization('Example Hospital','123456789');run=s.CaptureRun(org.organization_name,org.ein,'OH')
        url='https://charitableregistration.ohioago.gov/Charities/ChapterOrganizationDetails?Id=41158'
        text="Organization Name Example Hospital Employer Identification Number (EIN) 12-3456789 Registration Status Parent files on behalf of organization Annual Reports Filed Most Recent Report Filing Year N/A Fiscal Year End December Street Address 1 Main A Parent Organization Files on This Organization's Behalf"
        result=m.oh_result_from_detail_text(m.checker.StateResult(org.organization_name,org.ein,'OH','Unknown',''),text,url,'41158')
        row=m.response_data_for_lookup(result,text,org,run.name,run.ein,'OH',time.perf_counter())
        self.assertEqual(row['status'],'Exempt');self.assertIn("not a finding about the parent",row['comments'])
        run.document(url,fixture_image(text),'image',text)
        self.assertTrue(oh_detail_evidence.bound(run.documents[0],row,org.ein))
        self.persist(run,row)
        self.assertFalse(oh_detail_evidence.bound(run.documents[0],{**row,'matched_registry_identifier':'41159'},org.ein))
        self.assertFalse(oh_detail_evidence.bound(run.documents[0],row,'987654321'))

    def test_ca_current_exemption_selects_entity_original_not_retired_registration(self):
        org=m.checker.Organization('Example Research Institute','123456789')
        entity={'id':'5481653','entityStatus':'Exempt','entityName':org.organization_name,'fein':org.ein}
        retired={'id':'8901234','registrationType':'Charitable Organization','registrationStatus':'Merged Out',
                 'registrationNumber':'CT12345','currentExpirationDate':'2000-12-31',
                 'entityRelated':{'id':entity['id'],'name':org.organization_name+' - '+entity['id']}}
        with patch.object(m.checker,'ca_evoke_entity_search_by_ein',return_value=[entity]), \
             patch.object(m.checker,'ca_evoke_registrations_for_entity',return_value=[retired]):
            result=m.checker.search_ca(Mock(),org)
        self.assertTrue(result.success);self.assertEqual(result.status,'Exempt')
        self.assertEqual(result.matched_registry_identifier,entity['id'])
        self.assertIn('Merged Out',result.raw_status_text)
        self.assertIsNone(m.checker.ca_evoke_status_from_record(entity,[retired])[3])
        run=s.CaptureRun(org.organization_name,org.ein,'CA');v.remember_ca_selected(run,result)
        hint=run.source_detail_hints[entity['id']]
        self.assertTrue(hint['retired_registration_present'])
        self.assertEqual(hint['url'],'https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/5481653')
        self.assertNotIn('CT12345',run.source_detail_hints)
        text='Entity Details: Example Research Institute Exempt FEIN: 12-3456789 Entity Detail Entity Type Charity Entity Name Example Research Institute DBA None Entity Status Exempt Out of State? Yes'
        core=v.ca_exempt_entity_core(text,org.organization_name,org.ein)
        self.assertIsNotNone(core)
        self.assertIsNone(v.ca_exempt_entity_core(text.replace('12-3456789','98-7654321'),org.organization_name,org.ein))
        run.document(hint['url'],fixture_image(text),'image',core)
        row=m.response_data_for_lookup(result,result.raw_status_text,org,run.name,run.ein,'CA',time.perf_counter())
        self.persist(run,row)
        self.assertEqual(row['status'],'Exempt')
        for field,value in [('id','9999999'),('fein','987654321'),('entityStatus','Registered')]:
            changed=copy.deepcopy(result);changed._cc_selected_entity[field]=value
            rejected=s.CaptureRun(org.organization_name,org.ein,'CA');v.remember_ca_selected(rejected,changed)
            self.assertNotIn(entity['id'],getattr(rejected,'source_detail_hints',{}))

    def test_va_name_fallback_supplies_owned_detail_hint_without_claiming_source_ein(self):
        org=m.checker.Organization('Example Research Center','123456789')
        entity={'id':'opaqueEntityId','name':org.organization_name,'status':'Registered'}
        registration={'id':'opaqueRegistrationId','registrationNumber':'406093','type':'Registration',
            'registrationType':{'name':'Exempt Charity'},'entity':entity,
            'status':{'name':'Registered'},'renewalStatus':'Not Eligible','initialIssueDate':'2001-08-14'}
        with patch.object(m,'va_evoke_entity_search_by_ein',return_value=[]), \
             patch.object(m,'va_evoke_entity_search_by_name',return_value=[entity]), \
             patch.object(m,'va_evoke_registrations_for_entity_with_retry',return_value=([registration],[])):
            result=m.search_va_evoke_api(org)
        self.assertTrue(result.success);self.assertEqual(result.status,'Exempt')
        self.assertFalse(hasattr(result,'va_entity_evidence'))
        self.assertEqual(result._cc_va_selected_registration['source_ein'],'')
        run=s.CaptureRun(org.organization_name,org.ein,'VA');v.remember_va_selected(run,result)
        hint=run.source_detail_hints['406093']
        self.assertEqual(hint['url'],'https://vdacs.evokeplatform.com/app/publicPortal/registration/opaqueRegistrationId')
        self.assertEqual(hint['registration_type'],'ExemptCharity')
        self.assertEqual(hint['source_fields']['initialIssueDate'],'08/14/2001')
        for changes in [{'requested_ein':'987654321'},{'source_ein':'987654321'},{'id':'406094'},
                        {'entity_id':'differentEntity'},{'name':'Other Research Center'}]:
            other=copy.deepcopy(result);other._cc_va_selected_registration.update(changes)
            rejected=s.CaptureRun(org.organization_name,org.ein,'VA');v.remember_va_selected(rejected,other)
            self.assertFalse(getattr(rejected,'source_detail_hints',{}))

if __name__=='__main__':unittest.main()
