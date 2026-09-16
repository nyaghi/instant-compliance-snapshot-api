"""Expanded identity sources, query ordering, and no false negative contracts."""
import json, sys, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
EIN='050536854'; NAME="National Law Enforcement and Firefighters Children's Foundation"

class ExpandedDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.token=c.REVIEWED_NAME_CONTEXT.set({}); c.IDENTITY_SOURCE_CACHE.clear()
    def tearDown(self): c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def test_all_fifteen_states_plus_irs_scheduled(self):
        seen=[]
        def source(st,ein,deadline):
            seen.append(st);return {'source':st,'names':[],'complete':True}
        with patch.object(c,'identity_source_result',side_effect=source):r=c.discover_organization_names(NAME,EIN)
        self.assertEqual(set(seen),set('AK CA CO HI MA MD MI NM NJ NY OH OR PA VA WA IRS'.split()))
        self.assertEqual(len(seen),16);self.assertFalse(r['partial'])
    def test_structured_sources_never_take_other_ein_or_contact_names(self):
        fields={'VA':('ein','name'),'WA':('FEINNumber','EntityName'),'PA':('EIN','EntityName'),
                'MA':('Employer_Idendification_Number_EIN__c','Organization_Name__c'),'NJ':('crsm_federalein','name'),'NY':('ein','orgName')}
        for st,(ef,nf) in fields.items():
            with self.subTest(state=st):
                rows=[{ef:'05-0536854',nf:NAME,'OfficerName':'Wrong Person','AgentName':'Wrong Agent'},
                      {ef:'99-9999999',nf:NAME,'AKANames':'Wrong Chapter'}, {nf:'No EIN'}]
                names=c.identity_rows_names(st,rows,EIN,'https://state')['names']
                self.assertEqual([r['name'] for r in names],[NAME])
    def test_explicit_aliases_preserve_suffix_and_national_board_comma(self):
        self.assertEqual(c.identity_explicit_aliases('Example, Inc., Second Name'),['Example, Inc.','Second Name'])
        r=c.identity_rows_names('WA',[{'FEINNumber':EIN,'EntityName':NAME,'AKANames':"FIRST RESPONDERS CHILDREN'S FOUNDATION, NLEAFCF"}],EIN,'https://state')
        self.assertEqual([n['name'] for n in r['names']][-2:],["FIRST RESPONDERS CHILDREN'S FOUNDATION",'NLEAFCF'])
    def test_malformed_fields_never_become_names(self):
        for value in ['13-1624103','Inc','N/A','First Responders Children’s Foundatio','YWCA, Inc.stian Association of America, Inc']:
            with self.subTest(value=value):self.assertIsNone(c.identity_new_source_candidate(value,'MD','DBA','https://state'))
    def test_nm_identity_is_heading_ein_not_mission(self):
        source='<span id="MainContent_FormViewCharityDetail_LabelCharityName"><b>National Law Enforcement and Firefighters Children\'s Association (05-0536854)</b></span><p>Mission mentions Wrong Organization</p>'
        with patch.object(c,'identity_fetch',return_value=source.encode()):
            r=c.identity_nm_names(EIN,time.monotonic()+1)
            self.assertEqual([n['name'] for n in r['names']],["National Law Enforcement and Firefighters Children's Association"])
            with self.assertRaises(ValueError):c.identity_nm_names('131624103',time.monotonic()+1)
    def test_massachusetts_duplicate_label_is_not_an_identity(self):
        self.assertIsNone(c.identity_new_source_candidate('DUPLICATE OF #051545','MA','Registered name','https://state'))
        self.assertIsNotNone(c.identity_new_source_candidate('Duplicate Foundation','MA','Registered name','https://state'))
    def test_maryland_retains_legal_and_earlier_dbas_without_truncated_last_entry(self):
        row={'f_aedd5545-808f-4725-9b1d-5fa61e994a75':'Example Foundation','view_data':{'content_element_data':{
            'ein':'<strong>Charity EIN:</strong><var>05-0536854</var>',
            'dba':'<strong>Charity DBA Name(s):</strong><var>Complete Alias,Kesem Nationa</var>'}}}
        with patch.object(c,'identity_fetch',return_value=json.dumps({'success':True,'entries':[row],'total_count':1}).encode()):
            result=c.identity_md_names(EIN,time.monotonic()+5)
        self.assertEqual([n['name'] for n in result['names']],['Example Foundation','Complete Alias'])
        self.assertEqual(result['rejected_name_fields'],['Kesem Nationa'])
    def test_hi_requires_html_and_same_ein(self):
        source='<dt>Primary Name:</dt><dd>First Responders Childrens Foundation</dd><dt>FEIN:</dt><dd>05-0536854</dd>'
        with patch.object(c,'identity_fetch',return_value=source.encode()) as fetch:
            self.assertTrue(c.identity_hi_names(EIN,time.monotonic()+1)['complete'])
            self.assertEqual(fetch.call_args.kwargs['headers']['Accept'],'text/html')
            with self.assertRaises(ValueError):c.identity_hi_names('131624103',time.monotonic()+1)
    def test_new_york_signed_identity_query_is_ein_only(self):
        record={'organization_name':NAME,'ein':'05-0536854','purpose':'identity','completed':[]}
        with patch.object(c,'search_ny_direct') as registration:
            first=c.ny_connector_advance(record)
            self.assertEqual(first['query'],{'ein':EIN})
            record['completed']=[{'query':first['query'],'rows':[{'orgID':'01-02-03','orgName':NAME,'ein':'05-0536854'},
                {'orgID':'01-02-04','orgName':'Wrong Chapter','ein':'99-9999999'}]}]
            final=c.ny_connector_advance(record)['result']
            self.assertEqual([n['name'] for n in final['identity']['names']],[NAME]);registration.assert_not_called()
            self.assertNotIn('status',final)
    def test_removed_names_remain_removed_after_expansion(self):
        c.IDENTITY_SOURCE_CACHE[(EIN,'MD','live-v2')]=(time.time()+30,{'names':[c.identity_candidate('Removed','MD','DBA','https://state')]})
        self.assertNotIn('Removed',c.reviewed_queries_first(NAME,EIN,[NAME,'Generated'],limit=2))
    def test_approved_identities_precede_probes_and_all_keep_budget(self):
        aliases=tuple(f'Unique Alias {i}' for i in range(15));c.REVIEWED_NAME_CONTEXT.set({EIN:aliases})
        queries=c.reviewed_queries_first(NAME,EIN,['Firefighters',*aliases,NAME,'Law Enforcement'],limit=2)
        self.assertEqual(queries[:16],[NAME,*aliases]);self.assertEqual(queries[-2:],['Firefighters','Law Enforcement'])
        self.assertFalse(c.reviewed_identity_queries_completed(queries[:2],queries[:16]))
        self.assertTrue(c.reviewed_identity_queries_completed(queries[:16],queries[:16]))
    def test_no_alias_keeps_original_query_order_and_cap(self):
        original=['Distinctive','Original Name','Prefix']
        self.assertEqual(c.reviewed_queries_first(NAME,EIN,original,limit=2),original[:2])
    def test_wv_apostrophe_and_suffix_fallback_spellings_are_preserved(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('Another Identity Inc.',)})
        original="Children's Support, Inc."
        variants=[original,'Childrens Support','Children Support','Another Identity']
        result=c.reviewed_queries_first(original,EIN,variants,limit=8)
        self.assertEqual(result[:2],[original,'Another Identity Inc.'])
        for value in variants:self.assertIn(value,result)
    def test_nd_ms_me_wv_put_complete_names_before_probes(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:("First Responders Children's Foundation",'NLEAFCF')})
        org=c.checker.Organization(NAME,EIN)
        plans=[c.nd_search_queries(org),c.ms_preferred_search_variants(NAME,EIN),c.me_fast_direct_query_variants(org),c.wv_preferred_query_variants(NAME,EIN)]
        for plan in plans:
            keys=[c.identity_name_key(n) for n in plan]
            for identity in c.equivalent_name_queries(NAME,EIN):self.assertLess(keys.index(c.identity_name_key(identity)),3)
    def test_wrong_ein_chapter_address_protection_unchanged(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('First Responders Childrens Foundation',)})
        self.assertEqual(c.score_candidate(NAME,EIN,{'name':'First Responders Childrens Foundation','ein':'999999999'})['reason'],'REJECT_DIFFERENT_EIN')
        self.assertFalse(c.registry_name_is_safe_for_org('First Responders Childrens Foundation Wisconsin Chapter',NAME,EIN))
        self.assertEqual(c.registry_address_evidence(EIN,'Madison, WI',candidate_ein='999999999')['decision'],'different_ein')
    def test_wv_two_queries_cannot_skip_reviewed_identity(self):
        planned=['Primary','Alias One','Alias Two','Generated']
        self.assertFalse(c.wv_core_search_completed(planned[:2],planned,planned[:3]))
        self.assertTrue(c.wv_core_search_completed(planned[:3],planned,planned[:3]))
    def test_shared_name_search_uses_reviewed_identity_before_generated_probe(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('First Responders Childrens Foundation',)})
        searched=[]
        def search(page,org):
            searched.append(org.organization_name)
            return c.checker.StateResult(org.organization_name,org.ein,'SC',c.checker.STATUS_NOT_REGISTERED,'https://state',success=True)
        result=c.search_with_name_variants(None,c.checker.Organization(NAME,EIN),search,max_variants=1)
        self.assertEqual(searched[:2],[NAME,'First Responders Childrens Foundation'])
        self.assertEqual(c.public_status(result),'Not Registered')
    def test_shared_name_deadline_cannot_claim_negative_before_reviewed_alias(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('First Responders Childrens Foundation',)})
        def search(page,org):
            time.sleep(.01)
            return c.checker.StateResult(org.organization_name,org.ein,'SC',c.checker.STATUS_NOT_REGISTERED,'https://state',success=True)
        result=c.search_with_name_variants(None,c.checker.Organization(NAME,EIN),search,max_variants=1,max_elapsed_seconds=.001)
        self.assertFalse(result.success)
        self.assertNotEqual(c.public_status(result),'Not Registered')
    def test_fifteen_parallel_discoveries_are_ein_isolated(self):
        from concurrent.futures import ThreadPoolExecutor
        def source(st,ein,deadline):return {'source':st,'complete':True,'names':[c.identity_candidate('Org '+ein,st,'Legal','https://state')]}
        with patch.object(c,'identity_source_result',side_effect=source),ThreadPoolExecutor(max_workers=15) as pool:
            results=list(pool.map(lambda i:c.discover_organization_names('Org',str(100000000+i)),range(15)))
        for i,r in enumerate(results):self.assertEqual([n['name'] for n in r['names']],['Org '+str(100000000+i)])

if __name__=='__main__':unittest.main(verbosity=2)
