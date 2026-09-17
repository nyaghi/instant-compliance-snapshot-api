"""Expanded identity sources, query ordering, and no false negative contracts."""
import json, sys, time, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
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
    def test_completion_guard_accepts_supported_punctuation_spellings(self):
        for original in ['CLASSICAL 981 C/O JENNIFER RIDEWOOD', 'Example (National) Foundation', "Children's Support, Inc."]:
            with self.subTest(original=original):
                normalized=c.equivalent_name_queries(original,'')
                self.assertTrue(c.reviewed_identity_queries_completed([original],normalized))
                self.assertTrue(c.reviewed_identity_queries_completed(normalized,[original]))
    def test_completion_guard_never_credits_a_prefix_other_identity_or_failed_query(self):
        required=['Primary Foundation','Another Complete Identity']
        self.assertFalse(c.reviewed_identity_queries_completed(['Primary Foundation','Another'],required))
        self.assertFalse(c.reviewed_identity_queries_completed(['Primary Foundation','Other Complete Identity'],required))
        self.assertFalse(c.reviewed_identity_queries_completed(['Primary Foundation'],required))
        self.assertFalse(c.reviewed_identity_queries_completed([],required))
        self.assertTrue(c.reviewed_identity_queries_completed(required,required))
    def test_arkansas_complete_alias_search_and_unsearched_alias_are_distinguished(self):
        name='Classical 98.1';ein='273067797';alias='CLASSICAL 981 C/O JENNIFER RIDEWOOD'
        c.REVIEWED_NAME_CONTEXT.set({ein:(alias,)})
        org=c.checker.Organization(name,ein);page=MagicMock()
        with patch.object(c,'ar_wait_for_search_form',return_value=True),patch.object(c,'registry_page_body',return_value='Back to Search Form No Results Found'),patch.object(c,'ar_result_rows',return_value=[]),patch.object(c,'safe_wait_for_network_idle'):
            result=c.search_ar_precise(page,org)
            self.assertEqual(result.status,c.checker.STATUS_NOT_REGISTERED)
            self.assertTrue(result.success)
            with patch.object(c,'ar_reviewed_search_plan',return_value=([name],{})):
                partial=c.search_ar_precise(page,org)
            self.assertFalse(partial.success)
            self.assertNotEqual(partial.status,c.checker.STATUS_NOT_REGISTERED)
    def test_wv_apostrophe_and_suffix_fallback_spellings_are_preserved(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('Another Identity Inc.',)})
        original="Children's Support, Inc."
        variants=[original,'Childrens Support','Children Support','Another Identity']
        result=c.reviewed_queries_first(original,EIN,variants,limit=8)
        self.assertEqual(result[:2],[original,'Another Identity Inc.'])
        for value in variants:self.assertIn(value,result)
    def test_mississippi_searches_seventh_reviewed_name_and_reports_all_attempts(self):
        aliases=tuple(f'Unique Reviewed Identity {i}' for i in range(7))
        c.REVIEWED_NAME_CONTEXT.set({EIN:aliases});seen=[]
        module=c.state_batch_modules(['MS'])[c.load_state_batch_bundle().STATE_TO_MODULE['MS']]
        def search(page,org,navigate=True):
            seen.append(org.organization_name)
            matched=org.organization_name==aliases[-1]
            r=module.SearchResult(organization_name=org.organization_name,status='Current' if matched else module.STATUS_NOT_FOUND,raw_status_text='Registered' if matched else 'No matching organization row')
            r.success=True
            if matched:r.matched_registry_name=aliases[-1]
            return r
        with patch.object(c,'search_ms_fast',side_effect=search):r=c.search_batch_browser_state(None,c.checker.Organization(NAME,EIN),'MS')
        self.assertEqual(c.public_status(r),'Current')
        self.assertEqual(seen[:8],[NAME,*aliases]);self.assertEqual(r.queries_attempted,seen)
    def test_mississippi_cannot_certify_negative_after_omitted_or_incomplete_alias(self):
        aliases=('Second Reviewed Identity','Third Reviewed Identity')
        c.REVIEWED_NAME_CONTEXT.set({EIN:aliases})
        module=c.state_batch_modules(['MS'])[c.load_state_batch_bundle().STATE_TO_MODULE['MS']]
        def search(page,org,navigate=True):
            incomplete=org.organization_name==aliases[-1]
            r=module.SearchResult(organization_name=org.organization_name,status='Unable to Verify' if incomplete else module.STATUS_NOT_FOUND,raw_status_text='Search incomplete' if incomplete else 'No matching organization row')
            r.success=not incomplete;return r
        for variants in [[NAME],[NAME,*aliases]]:
            with self.subTest(variants=variants),patch.object(c,'reviewed_queries_first',return_value=variants),patch.object(c,'search_ms_fast',side_effect=search):
                r=c.search_batch_browser_state(None,c.checker.Organization(NAME,EIN),'MS')
                self.assertNotEqual(c.public_status(r),'Not Registered')
                self.assertEqual(r.source_confidence,'incomplete_search')
    def test_west_virginia_allows_larger_reviewed_list_but_still_bounds_slow_search(self):
        aliases=tuple(f'Unique Reviewed Identity {i}' for i in range(7));c.REVIEWED_NAME_CONTEXT.set({EIN:aliases})
        for seconds,expected in [(4.0,'Not Registered'),(20.0,'Unable to Verify')]:
            clock=[0.0];page=MagicMock()
            page.goto.side_effect=lambda *a,**k:clock.__setitem__(0,clock[0]+seconds)
            with self.subTest(seconds=seconds),patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(c,'registry_page_body',return_value='No records found'),patch.object(c,'safe_wait_for_network_idle'):
                r=c.search_wv_precise(page,c.checker.Organization(NAME,EIN))
            self.assertEqual(c.public_status(r),expected)
            self.assertLessEqual(clock[0],80)
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
    def test_louisiana_full_export_checks_all_reviewed_names_once(self):
        aliases=tuple(f'Unique Reviewed Identity {i}' for i in range(7));c.REVIEWED_NAME_CONTEXT.set({EIN:aliases})
        org=c.checker.Organization(NAME,EIN)
        unrelated=[{'Name':f'Unrelated Charity {i}','Registered Through':'12/31/2027'} for i in range(30)]
        for match in [False,True]:
            records=[*unrelated,*([{'Name':aliases[-1],'Registered Through':'12/31/2027'}] if match else [])]
            with self.subTest(match=match),patch.object(c,'weekly_asset',return_value=Path('fixture.xlsx')),patch.object(c,'la_registered_charities_rows_from_xlsx',return_value=records),patch.object(c,'search_la_downloaded_export',wraps=c.search_la_downloaded_export) as search:
                result=c.search_with_name_variants(None,org,search,max_variants=10,max_elapsed_seconds=.001)
                self.assertEqual(c.public_status(result),'Current' if match else 'Not Registered')
                self.assertEqual(search.call_count,1)
                if match:self.assertEqual(result.matched_registry_name,aliases[-1])
                else:self.assertTrue(c.reviewed_identity_queries_completed(result.queries_attempted,[NAME,*aliases]))
    def test_louisiana_incomplete_export_cannot_certify_no_record(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('Reviewed Alias',)})
        with patch.object(c,'weekly_asset',return_value=Path('fixture.xlsx')),patch.object(c,'la_registered_charities_rows_from_xlsx',return_value=[]):
            result=c.search_with_name_variants(None,c.checker.Organization(NAME,EIN),c.search_la_downloaded_export,max_variants=2,max_elapsed_seconds=.001)
        self.assertNotEqual(c.public_status(result),'Not Registered')
    def test_louisiana_ein_probe_does_not_count_as_full_name_search(self):
        records=[{'Name':f'Unrelated Charity {i}'} for i in range(30)]+[{'Name':NAME,'Registered Through':'12/31/2027'}]
        with patch.object(c,'build_search_queries',return_value=[EIN,NAME]),patch.object(c,'weekly_asset',return_value=Path('fixture.xlsx')),patch.object(c,'la_registered_charities_rows_from_xlsx',return_value=records):
            result=c.search_with_name_variants(None,c.checker.Organization(NAME,EIN),c.search_la_downloaded_export,max_variants=2)
        self.assertEqual(c.public_status(result),'Current')
        self.assertEqual(result.matched_registry_name,NAME)
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
