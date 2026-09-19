"""Public cross-state identity; no financial reads or organization exceptions."""
import copy,json,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class CrossStateTests(unittest.TestCase):
    def test_typographic_apostrophes_keep_literal_name_in_bounded_queries(self):
        for straight in ["Children's Hospital Los Angeles", "O'Brien Relief, Inc.", "Women's Learning Foundation"]:
            expected = None
            for apostrophe in ["'", "\u2019", "\u2018", "\u02bc", "\uff07"]:
                name = straight.replace("'", apostrophe)
                with self.subTest(name=name), patch.object(c, 'known_names_for_ein', return_value=[]):
                    queries = c.wi_search_names_for_org(c.checker.Organization(name, '123456789'))[:6]
                    if expected is None:
                        expected = queries
                    self.assertEqual(queries, expected)
                    self.assertTrue(any("'" in query for query in queries))

    def setUp(self):
        c.IDENTITY_SOURCE_CACHE.clear()
        self.ein='123456789';self.name='Regional Learning Association'
    def record(self,source='CA',**changes):
        return dict({'source':source,'ein':self.ein,'source_url':'https://state.example/public',
            'names':[self.name],'city':'Fort Myers','state':'FL','address_role':'organization'},**changes)
    def confirm(self,rows,locations=None,name=None):
        def cached(source,ein):return {'organization_records':[r for r in rows if r['source']==source]}
        with patch.object(c,'identity_cached_source_result',side_effect=cached),patch.object(c,'identity_source_result') as fetch:
            result=c.registry_cross_state_identity(self.ein,name or self.name,locations or ['FORT MYERS, FL'])
        fetch.assert_not_called();return result
    def test_exact_name_and_ein_bound_office_corroborate(self):
        result=self.confirm([self.record()])
        self.assertEqual(result['decision'],'corroborated')
        self.assertEqual(result['requested_ein'],self.ein)
    def test_second_public_office_can_resolve_irs_location_conflict(self):
        self.assertTrue(self.confirm([self.record()],['NEW YORK, NY','FORT MYERS, FL']))
    def test_wrong_ein_mailing_agent_city_state_or_name_cannot_clear_conflict(self):
        for changes in [{'ein':'999999999'},{'address_role':'mailing'},{'address_role':'agent'},
                        {'city':'Milwaukee'},{'state':'WI'},{'names':[self.name+' Wisconsin Chapter']},
                        {'names':[self.name+' Foundation']}]:
            with self.subTest(changes=changes):self.assertFalse(self.confirm([self.record(**changes)]))
    def test_missing_foundation_is_not_inferred_from_shared_city(self):
        self.assertFalse(self.confirm([self.record(names=[self.name+' Foundation'])],name=self.name))
    def test_minor_city_typo_requires_two_independent_states(self):
        self.assertFalse(self.confirm([self.record()],['FORT MEYERS, FL']))
        self.assertFalse(self.confirm([self.record(),self.record()],['FORT MEYERS, FL']))
        self.assertTrue(self.confirm([self.record(),self.record('CO')],['FORT MEYERS, FL'])['minor_city_spelling_difference'])
    def test_multiple_name_or_city_edits_are_not_permitted(self):
        self.assertFalse(self.confirm([self.record(),self.record('CO')],['FORT MARS, FL']))
        self.assertFalse(self.confirm([self.record(),self.record('CO')],name='Regional Teaching Association'))
    def test_cached_irs_header_and_state_record_can_corroborate_minor_city_typo(self):
        irs={'names':[{'name':self.name,'verified':True}],
             'address':{'ein':self.ein,'city':'Fort Myers','state':'FL'}}
        def cache(source,ein):
            return irs if source=='IRS' else {'organization_records':[self.record('CO')]} if source=='CO' else None
        with patch.object(c,'identity_cached_source_result',side_effect=cache),patch.object(c,'identity_source_result',side_effect=TimeoutError) as fetch:
            self.assertTrue(c.registry_cross_state_identity(self.ein,self.name,['FORT MEYERS, FL']))
            self.assertTrue(all(call.args[0]!='IRS' for call in fetch.call_args_list))
            irs['address']['ein']='999999999'
            self.assertFalse(c.registry_cross_state_identity(self.ein,self.name,['FORT MEYERS, FL']))
    def test_two_irs_headers_are_not_two_independent_sources(self):
        address={'ein':self.ein,'city':'Fort Myers','state':'FL'}
        irs={'names':[{'name':self.name,'verified':True}],'address':address,'filer_address':address}
        with patch.object(c,'identity_cached_source_result',side_effect=lambda source,ein:irs if source=='IRS' else {'organization_records':[]}):
            self.assertFalse(c.registry_cross_state_identity(self.ein,self.name,['FORT MEYERS, FL']))
    def test_missing_sources_do_not_confirm_an_organization(self):
        with patch.object(c,'identity_cached_source_result',return_value=None),patch.object(c,'identity_source_result',side_effect=TimeoutError):
            self.assertFalse(c.registry_cross_state_identity(self.ein,self.name,['FORT MYERS, FL']))
    def test_ca_captures_only_same_ein_official_not_mailing_address(self):
        rows=[{'fein':'12-3456789','legalName':self.name,'officialAddress':{'city':'Fort Myers','state':'FL'},'mailingAddress':{'city':'Rockville','state':'MD'}},
              {'fein':'99-9999999','legalName':self.name,'officialAddress':{'city':'Milwaukee','state':'WI'}}]
        with patch.object(c,'identity_fetch',return_value=json.dumps(rows).encode()):result=c.identity_ca_names(self.ein,time.monotonic()+3)
        self.assertEqual(len(result['organization_records']),1);self.assertEqual(result['organization_records'][0]['city'],'Fort Myers')
    def test_bad_address_does_not_break_existing_name_discovery(self):
        with patch.object(c,'identity_fetch',return_value=json.dumps([{'fein':'12-3456789','legalName':self.name,'officialAddress':'unknown'}]).encode()):result=c.identity_ca_names(self.ein,time.monotonic()+3)
        self.assertEqual(result['names'][0]['name'],self.name);self.assertFalse(result['organization_records'][0]['city'])
    def test_co_only_latest_principal_office_per_entity_is_used(self):
        rows=[{'fein':'12-3456789','name':self.name,'entityid':'1','principalcity':'Fort Myers','principalstate':'FL','mailingcity':'Rockville'},
              {'fein':'12-3456789','name':'Former Learning Name','entityid':'1','principalcity':'Boston','principalstate':'MA'}]
        with patch.object(c,'identity_fetch',return_value=json.dumps(rows).encode()):result=c.identity_co_names(self.ein,time.monotonic()+3)
        self.assertEqual(len(result['names']),2);self.assertEqual(len(result['organization_records']),1)
        self.assertEqual(result['organization_records'][0]['city'],'Fort Myers')
    def test_foundation_flow_never_calls_financial_page(self):
        candidate=c.wi_foundation_identity_review(self.name,self.name+' Foundation','76543-800','CredSummaryDetails.aspx?chid=123','07/31/2027','FORT MYERS, FL')
        detail=f'Name: {self.name} Credential Type: Charitable Organization Credential Number: 76543-800 Location: Fort Myers, FL Status License is current (Active)'
        proof=self.confirm([self.record()])
        with patch.object(c,'wi_http_detail_text',return_value=detail),patch.object(c,'registry_cross_state_identity',return_value=proof), \
             patch.object(c,'wi_foundation_filing_identity') as financial,patch.object(c,'wi_identity_page') as page:
            result=c.wi_confirm_cross_state_credential(candidate,self.name+' Foundation',self.ein)
        self.assertFalse(result['identity_conflict']);financial.assert_not_called();page.assert_not_called()
        self.assertTrue(c.wi_reviewed_credential_identity(self.name+' Foundation',self.ein,result))
        tampered=copy.deepcopy(result);tampered['reviewed_identity_evidence']['requested_ein']='999999999'
        self.assertFalse(c.wi_reviewed_credential_identity(self.name+' Foundation',self.ein,tampered))
    def test_foundation_flow_requires_same_credential_and_live_status(self):
        candidate=c.wi_foundation_identity_review(self.name,self.name+' Foundation','76543-800','CredSummaryDetails.aspx?chid=123','07/31/2027')
        for detail in ['Loading',f'Name: {self.name} Credential Type: Charitable Organization Credential Number: 99999-800',
                       f'Name: {self.name} Credential Type: Charitable Organization Credential Number: 76543-800']:
            with self.subTest(detail=detail),patch.object(c,'wi_http_detail_text',return_value=detail),patch.object(c,'wi_reader_text',return_value=detail),patch.object(c,'registry_cross_state_identity',return_value=self.confirm([self.record()])):
                self.assertTrue(c.wi_confirm_cross_state_credential(candidate,self.name+' Foundation',self.ein)['identity_conflict'])

if __name__=='__main__':unittest.main(verbosity=2)
