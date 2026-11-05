"""Offline behavior checks for the Gates 22/23 package and adjacent controls."""
import copy,socket,time,unittest
from unittest.mock import patch
import registry_snapshot_server as m
from deployment import state_snapshots as ss,fl_response_evidence as fl
from testing.capacity_lab.test_fl_business_lookup import BusinessLookup,source,card


class StatusAndIdentity(unittest.TestCase):
    def setUp(self):
        p=patch.object(socket,'create_connection',side_effect=AssertionError('Unexpected network in local check'))
        p.start();self.addCleanup(p.stop)

    def test_normalized_duplicate_alias_must_not_disable_institution_guard(self):
        name="The Children's Hospital of Philadelphia";ein='231352166'
        request=m.normalize_organization_requests({'organization_name':name,'ein':ein,
            'alternate_names':['The Childrens Hospital Of Philadelphia']},privileged=False)[0]
        self.assertEqual(request['alternate_names'],[])
        for aliases in [[],['The Childrens Hospital Of Philadelphia']]:
            token=m.REVIEWED_NAME_CONTEXT.set({ein:aliases})
            try:
                for candidate in ["THE CHILDREN'S HOSPITAL OF PHILADELPHIA FOUNDATION",
                        "CHILDREN'S HOSPITAL OF PHILADELPHIA FOUNDATION (THE)",
                        'Childrens Hospital of Philadelphia Foundation']:
                    self.assertFalse(m.reviewed_name_candidate_is_safe(candidate,name,ein))
                    self.assertFalse(m.registry_name_is_safe_for_org(candidate,name,ein))
                    self.assertFalse(m.ky_snapshot_registry_name_is_safe(candidate,[name],name,ein))
                    self.assertEqual(m.score_candidate(name,ein,{'name':candidate,'ein':'232237932'})['decision'],'rejected')
            finally:m.REVIEWED_NAME_CONTEXT.reset(token)

    def test_same_ein_and_explicit_reviewed_legal_name_remain_supported(self):
        for name in ['Example Hospital','Example University','Example Medical Clinic','Example Health System']:
            foundation=name+' Foundation';ein='123456789'
            self.assertEqual(m.score_candidate(name,ein,{'name':foundation,'ein':ein})['decision'],'accepted')
            token=m.REVIEWED_NAME_CONTEXT.set({ein:[foundation]})
            try:self.assertTrue(m.registry_name_is_safe_for_org(foundation,name,ein))
            finally:m.REVIEWED_NAME_CONTEXT.reset(token)
            self.assertTrue(m.registry_name_is_safe_for_org(name,name,ein))

    def test_ca_exempt_entity_is_not_closed_by_merged_out_credential(self):
        for name in ['Scripps Research Institute','Fred Hutchinson Cancer Center','Independent Research Institute']:
            entity={'entityStatus':'Exempt','name':name}
            reg={'registrationType':'Charitable Organization','registrationStatus':'Merged Out','registrationNumber':'CT1234'}
            status,raw,identifier,_=m.checker.ca_evoke_status_from_record(entity,[reg])
            self.assertEqual(status,'Exempt');self.assertIn('Merged Out',raw);self.assertEqual(identifier,'CT1234')
            for standing,expected in [('Suspended','Suspended'),('Revoked','Revoked'),('Closed','Closed / Withdrawn / Canceled')]:
                self.assertEqual(m.checker.ca_evoke_status_from_record({'entityStatus':standing},[reg])[0],expected)
            self.assertEqual(m.checker.ca_evoke_status_from_record(entity,[dict(reg,reportingStatus='Enforcement')])[0],'Suspended')
            self.assertEqual(m.checker.ca_evoke_status_from_record({'entityStatus':'Registered'},[reg])[0],'Closed / Withdrawn / Canceled')

    def test_oh_explicit_filing_exemption_and_adverse_controls(self):
        for standing,expected in [('Not Required to File','Exempt'),('Not Required to Register','Exempt'),
                ('Pending','Pending'),('Revoked','Revoked'),('Suspended','Suspended'),('Closed','Closed / Withdrawn / Canceled')]:
            result=m.checker.StateResult('Example Hospital','123456789','OH','Unknown','')
            body=f'Organization Name Example Hospital EIN 12-3456789 Registration Status {standing} Annual Reports Filed Most Recent Report Filing Year N/A Fiscal Year End December Street Address 1 Main'
            result=m.oh_result_from_detail_text(result,body,'https://charitableregistration.ohioago.gov/Charities/Organization/123','123')
            self.assertEqual(result.status,expected)

    def test_tn_old_financials_do_not_invent_an_expiration(self):
        fields={'Name':'Example Research Institute','CO Number':'CO27470','Status':'Active',
            'Registration Date':'09/26/2016','Expiration Date':'','Address':'',
            'financial_periods':['09/30/2019','09/30/2020'],'financial_count':2}
        row={'name':fields['Name'],'city':'','region':''}
        result=m.tn_charity_detail_evidence(fields,'CO27470',row)
        self.assertEqual(result['status'],'Current');self.assertIsNone(result['expiration'])
        self.assertEqual(result['latest_filed_period'].isoformat(),'2020-09-30')
        for raw,expected in [('Revoked','Revoked'),('Suspended','Suspended'),('Exempt','Exempt')]:
            self.assertEqual(m.tn_charity_detail_evidence({**fields,'Status':raw},'CO27470',row)['status'],expected)
        explicit=m.tn_charity_detail_evidence({**fields,'Expiration Date':'09/30/2020'},'CO27470',row)
        self.assertEqual(explicit['status'],'Delinquent');self.assertEqual(explicit['expiration'].isoformat(),'2020-09-30')
        with self.assertRaises(ValueError):m.tn_charity_detail_evidence({**fields,'financial_count':3},'CO27470',row)

    def test_ma_hyphenated_actual_period_requires_identity_and_complete_dates(self):
        text='Form PC AG Number 046070 FEIN 34-0714585 Report for the Fiscal Period: 01-01-2020 to 12-31-2020'
        result=m.ma_scanned_form_pc_evidence(text,2020,'046070','340714585')
        self.assertEqual(result['period_end'],'12/31/2020')
        for changed in [text.replace('34-0714585','12-3456789'),text.replace('046070','046071'),
                text.replace('01-01-2020','01-01-2018'),text.replace('12-31-2020','12-31-202'),
                text.replace(' to ',' or '),text.replace('Form PC','Schedule A')]:
            self.assertEqual(m.ma_scanned_form_pc_evidence(changed,2020,'046070','340714585'),{})
        self.assertEqual(m.ma_scanned_form_pc_evidence(text,2021,'046070','340714585'),{})

    def test_nv_composite_requires_only_complete_reviewed_names(self):
        ein='123456789';name='Example Research Foundation';aliases=['Example Museum','Example Collection']
        token=m.REVIEWED_NAME_CONTEXT.set({ein:aliases})
        try:
            combined=name+' '+', '.join(aliases)
            self.assertEqual(m.nv_reviewed_compound_names(combined,name,ein),[name,*aliases])
            for label in [combined+' Regional Affiliate',name+' Foundation',name+' Example',
                    'Unknown Research Foundation '+', '.join(aliases),name]:
                self.assertEqual(m.nv_reviewed_compound_names(label,name,ein),[])
            with patch.object(m,'trial_identity',return_value=True):
                scores=m.final_four_search_candidate_scores(name,ein,'NV',{'name':combined,'ein':'987654321'})
                self.assertTrue(all(x['decision']=='rejected' for x in scores))
                scores=m.final_four_search_candidate_scores(name,ein,'NV',{'name':combined,'ein':''})
                self.assertTrue(any(x['decision']=='accepted' for x in scores))
        finally:m.REVIEWED_NAME_CONTEXT.reset(token)

    def test_oh_parent_filing_requires_both_explicit_source_statements(self):
        url='https://charitableregistration.ohioago.gov/Charities/ChapterOrganizationDetails?Id=41158'
        body="Organization Name Example Hospital EIN 12-3456789 Registration Status Parent files on behalf of organization Annual Reports Filed Most Recent Report Filing Year N/A Fiscal Year End December Street Address 1 Main A Parent Organization Files on This Organization's Behalf"
        def parse(text,source=url):
            return m.oh_result_from_detail_text(m.checker.StateResult('Example Hospital','123456789','OH','Unknown',''),text,source,'41158')
        result=parse(body)
        self.assertEqual(result.status,'Exempt');self.assertIn("not a finding about the parent",result.source_note)
        self.assertNotEqual(parse(body.replace("A Parent Organization Files on This Organization's Behalf",'')).status,'Exempt')
        self.assertNotEqual(parse(body,url.replace('ChapterOrganizationDetails','OrganizationDetails')).status,'Exempt')


class FloridaExemption(BusinessLookup):
    def test_educational_exemption_uses_original_source_and_survives_public_binding(self):
        html=source(card(status='Law NA - Educational',expiry='01/01/20'))
        run=ss.CaptureRun(self.org.organization_name,self.org.ein,'FL');token=ss.CURRENT.set(run)
        m.PUBLIC_PROFILE_CACHE[self.org.ein]={}
        try:
            self.assertTrue(fl.remember_response(m,html,run.name))
            result=self.run_source(html)
            self.assertEqual(result.status,'Exempt');self.page.goto.assert_not_called()
            self.assertEqual(result.matched_registry_identifier,'CH12345')
            public=m.response_data_for_lookup(result,result.raw_status_text,self.org,run.name,run.ein,'FL',time.perf_counter())
            self.assertEqual(public['status'],'Exempt')
            self.assertEqual(run.fl_response_proof['public_binding'],fl.binding(public))
            self.assertIsNotNone(fl.capture_bound(run,public))
            self.assertFalse(fl.image_bound(run,{**public,'matched_registry_identifier':'CH999'},fl.URL,b'foreign','image'))
        finally:ss.CURRENT.reset(token)

if __name__=='__main__':unittest.main()
