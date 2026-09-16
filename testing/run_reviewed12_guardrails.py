"""Identity, address, query completion and short-year regression contracts."""
import io,json,re,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
F=Path(__file__).parent/'fixtures/reviewed12'

class ReviewedTwelveTests(unittest.TestCase):
    def setUp(self):
        self.token=c.REVIEWED_NAME_CONTEXT.set({})
    def tearDown(self):c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def scope(self,ein,names):c.REVIEWED_NAME_CONTEXT.set({c.canonical_ein_digits(ein):tuple(names)})
    def test_dba_list_keeps_corporate_suffix_and_separates_actual_names(self):
        self.assertEqual(c.identity_dba_list('Alpha, Inc.; Beta Foundation; Gamma, LLC'),['Alpha, Inc.','Beta Foundation','Gamma, LLC'])
        self.assertEqual(c.identity_dba_list('Red Nose Day Foundation, Charity Projects Entertainment Fund, America Gives Back'),['Red Nose Day Foundation','Charity Projects Entertainment Fund','America Gives Back'])
        for name in ['YWCA, Boston','Helping People Everywhere, Los Angeles','Alpha, Inc.']:
            self.assertEqual(c.identity_dba_list(name),[name])
    def test_california_semicolon_discovery_produces_two_search_names(self):
        payload=[{'fein':'46-3408177','entityName':'Christian Ministry Alliance','dba':'Association of Christian Nonprofits; Donor Fund'}]
        with patch.object(c,'identity_fetch',return_value=json.dumps(payload).encode()):r=c.identity_ca_names('463408177',time.monotonic()+1)
        self.assertEqual([n['name'] for n in r['names']],['Christian Ministry Alliance','Association of Christian Nonprofits','Donor Fund'])
        self.assertEqual(r['names'][1]['evidence'][0]['original_field'],payload[0]['dba'])
    def test_missing_period_does_not_erase_same_ein_names(self):
        source=(F/'prevent-latest-irs.html').read_text(encoding='utf-8')
        source=re.sub(r'(<span[^>]*TaxPeriodEndDt[^>]*>)[^<]*',r'\1unreadable',source)
        r=c.irs_header_evidence(source,'237235671','https://source',require_period=False)
        self.assertTrue(r['names']);self.assertTrue(r['period_unconfirmed'])
        with self.assertRaises(ValueError):c.irs_header_evidence(source,'999999999','https://source',require_period=False)
    def test_valid_previous_form_short_year(self):
        r=c.irs_header_evidence((F/'prevent-latest-irs.html').read_text(encoding='utf-8'),'237235671','https://source')
        self.assertEqual((r['filing']['tax_year_label'],r['filing']['period_begin'],r['filing']['period_end']),(2024,'2025-01-01','2025-03-31'))
    def test_prior_form_cannot_describe_unrelated_full_calendar_year(self):
        self.assertFalse(c.irs_form_period_is_valid(c.date(2025,1,1),c.date(2025,12,31),2024))
        self.assertFalse(c.irs_form_period_is_valid(c.date(2026,1,1),c.date(2026,3,31),2024))
    def test_autism_actual_short_period_remains_june(self):
        r=c.irs_header_evidence((F/'autism-2025-irs.html').read_text(encoding='utf-8'),'952548452','https://source')['filing']
        self.assertEqual(r['period_end'],'2025-06-30')
        result=c.checker.StateResult('Autism Research Institute','95-2548452','KY','Current','')
        result.matched_registry_identifier='13927';r.update(short_period_fiscal_end_confirmed=True,period_basis='Same-EIN header and fiscal metadata')
        c.annotate_irs_based_state_period(result,r)
        self.assertEqual(result.computed_due_date,'11/16/2026');self.assertEqual(result.matched_registry_identifier,'13927')
    def test_missing_dates_assumption_is_disclosed(self):
        result=c.checker.StateResult('Fixture','20-3588745','HI','Current','')
        result.raw_status_text='Registration Status: Active';result.matched_registry_identifier='retained'
        c.annotate_irs_based_state_period(result,c.assumed_calendar_period(result.ein,2025,'https://state'))
        comment=c.comments_for_result_base(result,'','Current')
        self.assertIn('December 31 is assumed',comment);self.assertIn('estimates',comment)
        self.assertNotIn('The corresponding return covers',comment);self.assertEqual(result.computed_due_date,'5/17/2027')
        self.assertEqual(result.matched_registry_identifier,'retained')
    def test_uncertain_scanned_header_after_cover_uses_disclosed_fallback(self):
        body=(F/'firehouse-first-three.pdf').read_bytes()
        r=c.form990_pdf_period(body,'20-3588745',2025,'https://state',time.monotonic()+20)
        if r:
            self.assertEqual(r.get('period_end'),'2025-12-31');self.assertEqual(r.get('pdf_page'),3)
        else:
            # Low-confidence OCR is not proof of empty fiscal date boxes.
            # The approved explicit assumption remains available after reading fails.
            from types import SimpleNamespace
            page=SimpleNamespace(content=lambda:'<div id="irs_2025">990</div>',url='https://state')
            with patch.object(c,'hi_attachment_period',return_value={}),patch.object(c,'irs_period_for_label',return_value={}):
                fallback=c.hi_public_filing_period(page,'20-3588745')
            self.assertTrue(fallback['period_assumed']);self.assertEqual(fallback['period_end'],'2025-12-31')
    def test_annual_state_filing_is_not_replaced_by_later_short_return(self):
        annual={'ein':'237235671','tax_year_label':2024,'period_begin':'2024-01-01','period_end':'2024-12-31'}
        short={**annual,'period_begin':'2025-01-01','period_end':'2025-03-31'}
        c.TAX_PERIOD_EVIDENCE_CACHE.clear()
        index=b'/organizations/237235671/202522679349200017/full /organizations/237235671/202422679349200018/full'
        with patch.object(c,'identity_source_result',return_value={'filing':short}),patch.object(c,'identity_fetch',return_value=index),patch.object(c,'irs_return_header',side_effect=[ValueError('Unreadable'),{'filing':annual}]):
            evidence=c.irs_period_for_label('237235671',2024,time.monotonic()+10)
        self.assertEqual(evidence['period_end'],'2024-12-31');self.assertEqual(evidence['next_known_period_end'],'2025-03-31')
        c.TAX_PERIOD_EVIDENCE_CACHE.clear()
    def test_current_name_outranks_long_historical_alias(self):
        self.scope('131084135',['National Association for the Advancement of Colored People'])
        primary=c.registry_identity_preference('NAACP Empowerment Programs Inc','NAACP Empowerment Programs','131084135')
        historical=c.registry_identity_preference('National Association for the Advancement of Colored People','NAACP Empowerment Programs','131084135')
        self.assertGreater(primary,historical)
    def test_maine_primary_query_stays_first_after_prefix_deduplication(self):
        self.scope('131084135',['National Association for the Advancement of Colored People'])
        queries=c.me_fast_direct_query_variants(c.checker.Organization('NAACP Empowerment Programs, Inc.','13-1084135'))
        self.assertTrue(queries[0].upper().startswith('NAACP'),queries)
    def test_wisconsin_distinct_alias_inside_six_slots(self):
        self.scope('010885377',['COMIC RELIEF INC.','AMERICA GIVES BACK, INC.','CHARITY PROJECTS ENTERTAINMENT FUND'])
        queries=c.wi_search_names_for_org(c.checker.Organization('Comic Relief, Inc.','01-0885377'))[:6]
        self.assertIn('CHARITY PROJECTS ENTERTAINMENT FUND',queries)
        self.assertEqual(len(queries),len({q.casefold() for q in queries}))
    def test_wisconsin_plain_ywca_name_inside_six_slots(self):
        self.scope('131624103',['YWCA U.S.A., INC.','National Board of the YWCA of the USA'])
        queries=c.wi_search_names_for_org(c.checker.Organization('YWCA USA, Inc.','13-1624103'))[:6]
        self.assertEqual(queries[0],'YWCA USA')
    def test_wisconsin_rejects_regional_primary_even_with_national_alias(self):
        self.scope('362934689',['RONALD MCDONALD HOUSE CHARITIES, INC.'])
        detail=json.loads((F/'wi-detail-25435-800.json').read_text())['text']
        candidate={'license_number':'25435-800','registry_name':'RONALD MCDONALD HOUSE CHARITIES'}
        self.assertIsNone(c.wi_verify_candidate_identity(candidate,c.organization_match_target_variants('Ronald McDonald House Global / RMHC','362934689'),'Ronald McDonald House Global / RMHC','362934689',detail))
    def test_national_wi_credential_has_chicago_address(self):
        self.scope('362934689',['RONALD MCDONALD HOUSE CHARITIES, INC.'])
        detail=json.loads((F/'wi-detail-2812-800.json').read_text())['text']
        candidate={'license_number':'2812-800','registry_name':'RONALD MCDONALD HOUSE CHARITIES INC'}
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'ein':362934689,'city':'Chicago','state':'IL'}}):
            result=c.wi_verify_candidate_identity(candidate,c.organization_match_target_variants('Ronald McDonald House Global / RMHC','362934689'),'Ronald McDonald House Global / RMHC','362934689',detail)
        self.assertFalse(result['identity_conflict']);self.assertEqual(result['address_evidence']['decision'],'corroborated')
    def test_address_conflict_cannot_confirm_same_name(self):
        profile={'organization':{'ein':123456789,'city':'Chicago','state':'IL'}}
        with patch.object(c,'public_profile_for_ein',return_value=profile):
            for city in ['Milwaukee, WI','Madison, WI','Salt Lake City, UT']:
                self.assertEqual(c.registry_address_evidence('123456789',city)['decision'],'conflict')
            self.assertEqual(c.registry_address_evidence('123456789','Chicago, IL')['decision'],'corroborated')
            self.assertEqual(c.registry_address_evidence('123456789','Madison, WI',role='registered_agent')['decision'],'unavailable')
    def test_exact_ein_overrides_old_address_and_same_address_never_overrides_wrong_ein(self):
        self.assertEqual(c.registry_address_evidence('123456789','Madison, WI',candidate_ein='123456789')['decision'],'same_ein')
        self.assertEqual(c.registry_address_evidence('123456789','Chicago, IL',candidate_ein='987654321')['decision'],'different_ein')
    def test_missing_address_does_not_reject(self):
        self.assertEqual(c.registry_address_evidence('123456789','')['decision'],'unavailable')
    def test_same_credential_may_list_more_than_one_organization_address(self):
        detail='Name: YWCA USA INC Credential Type: CHARITABLE ORGANIZATION Credential Number: 3108-800 Location: MESA, AZ Status License is current (Active)'
        row={'license_number':'3108-800','registry_name':'YWCA USA','location':'WASHINGTON, DC'}
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'ein':131624103,'city':'Washington','state':'DC'}}):
            result=c.wi_verify_candidate_identity(row,['YWCA USA'],'YWCA USA','131624103',detail)
        self.assertFalse(result['identity_conflict']);self.assertEqual(result['address_evidence']['other_registry_location'],'MESA, AZ')
    def test_incomplete_wi_query_is_not_a_negative(self):
        def incomplete(names,targets,deadline,**kwargs):
            kwargs['progress']['attempted'].append(names[0]);kwargs['progress']['completed'].add(names[0]);return None,True
        org=c.checker.Organization('Fixture National Foundation','123456789')
        self.scope(org.ein,['Fixture Former Name'])
        with patch.object(c,'wi_http_search_best_match',side_effect=incomplete),patch.object(c,'wi_reader_search_best_match',return_value=(None,False)):
            result=c.search_wi(None,org)
        self.assertEqual(result.status,'Site Not Reachable');self.assertEqual(len(result.queries_attempted),1)
    def test_wi_empty_table_skeleton_is_not_completed_no_results(self):
        self.assertFalse(c.wi_has_complete_results('<table id="OrgCredentialSearch_gvCredentialSearchResults"><tr><th>Name</th></tr></table>'))
        self.assertTrue(c.wi_has_complete_results('There are no query results'))
    def test_last_wi_fallback_requires_every_required_name(self):
        org=c.checker.Organization('Primary Name','123456789')
        with patch.object(c,'equivalent_name_queries',return_value=['Primary Name','Former Name']),patch.object(c,'wi_search_names_for_org',return_value=['Primary Name','Former Name']),patch.object(c,'wi_reader_text',side_effect=['Organization Search Results There are no query results','']):
            self.assertIsNone(c.wi_confirm_clean_no_results_page(org))
    def test_unreadable_newer_credential_cannot_make_old_expired_record_conclusive(self):
        old={'registry_name':'Reading Partners','score':5,'expiration_date':c.date(2019,7,31),'detail_status':'License is not current (Expired)','identity_conflict':False}
        newer={**old,'expiration_date':c.date(2027,7,31),'detail_status':'','identity_conflict':True,'identity_detail_unavailable':True}
        self.assertTrue(c.wi_better_candidate(newer,old));self.assertFalse(c.wi_better_candidate(old,newer))
    def test_wisconsin_reader_requests_fresh_search_pages(self):
        with patch.object(c,'wi_reader_text',return_value='There are no query results') as read:
            c.wi_reader_search_best_match(['Reading Partners'],['Reading Partners'])
        self.assertTrue(read.call_args.kwargs['no_cache'])
    def test_equivalent_ct_records_still_prefer_active(self):
        self.scope('050536854',["National Law Enforcement and Firefighters Children's Foundation"])
        org=c.checker.Organization("First Responders Children's Foundation",'05-0536854')
        rows=json.loads((F/'ct-direct-evidence.json').read_text())
        candidates=[]
        for search in rows:
            for row in search.get('rows',[]):
                with patch.object(c,'ct_direct_detail_text',return_value=row['detail']):
                    result,_=c.ct_direct_result_from_row(org,row['html'],c.organization_match_target_variants(org.organization_name,org.ein),'https://state')
                if result:candidates.append(result)
        self.assertEqual(max(candidates,key=lambda r:r.selection_rank).matched_registry_identifier,'CHR.0013079')
    def test_explicit_local_chapter_remains_eligible(self):
        name='Ronald McDonald House Charities of the Intermountain Area Inc'
        self.assertTrue(c.wi_live_candidate_name_is_safe(name,[name],name,'999999999'))
    def test_five_ten_fifteen_workflows_keep_reviewed_names_isolated(self):
        from concurrent.futures import ThreadPoolExecutor
        states=['AK','AR','CA','CO','CT','FL','HI','KS','KY','LA','MA','MD','ME','MI','MN','MS','ND','NH','NJ','NM','NY','OH','OK','OR','PA','SC','VA','WA','WI','WV']
        def registry(name,ein,state,**kwargs):
            time.sleep(.001)
            aliases=c.known_names_for_ein(ein)
            self.assertEqual(aliases,[name+' Former Name'])
            return {'organization_name':name,'ein':ein,'state':state,'status':'Current','matched_registry_name':name,'success':True}
        def workflow(index):
            name=f'Fixture Organization {index}';ein=f'{100000000+index}'
            return c.run_state_lookups_parallel([{'organization_name':name,'ein':ein,'alternate_names':[name+' Former Name']}],states)
        with patch.object(c,'BATCH_FANOUT_SINGLE_STATE_LOOKUPS',False),patch.object(c,'run_state_lookup_for_batch',side_effect=registry),patch.object(c,'confirm_fragile_batch_results',side_effect=lambda rows:rows):
            for count in [5,10,15]:
                with ThreadPoolExecutor(max_workers=count) as pool: results=list(pool.map(workflow,range(count)))
                self.assertEqual(sum(len(rows) for rows in results),count*30)
        self.assertEqual(c.known_names_for_ein('100000000'),[])

if __name__=='__main__':unittest.main()
