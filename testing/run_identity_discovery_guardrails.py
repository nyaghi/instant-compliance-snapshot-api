"""Identity evidence, review isolation, and deadline contracts; no live services."""
import concurrent.futures, json, sys, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

EIN='131624103'
def header(ein=EIN, begin='07-01-2024', end='06-30-2025', dba=''):
    values={'ReturnHeader[1]/Filer[1]/EIN[1]':ein,
            'ReturnHeader[1]/Filer[1]/BusinessName[1]/BusinessNameLine1Txt[1]':'YWCA USA INC',
            'ReturnHeader[1]/TaxPeriodBeginDt[1]':begin,'ReturnHeader[1]/TaxPeriodEndDt[1]':end,
            'SubmissionDocument/IRS990[1]/DoingBusinessAsName[1]/BusinessNameLine1Txt[1]':dba,
            'SubmissionDocument/IRS990ScheduleI[1]/RecipientBusinessName[1]':'Wrong Affiliate',
            'ReturnHeader[1]/PreparerFirmGrp[1]/PreparerFirmName[1]':'Wrong Preparer'}
    return '<title>TY 2024 Form 990</title>'+''.join(f'<span id="/AppData/SubmissionHeaderAndDocument/{k}">{v}</span>' for k,v in values.items())

class IdentityTests(unittest.TestCase):
    def setUp(self):
        c.IDENTITY_SOURCE_CACHE.clear(); self.token=c.REVIEWED_NAME_CONTEXT.set({})
    def tearDown(self): c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def test_dedupe_preserves_meaningful_identity(self):
        self.assertEqual(c.identity_name_key('YWCA USA, Inc.'),c.identity_name_key('ywca usa Incorporated'))
        self.assertNotEqual(c.identity_name_key('YWCA USA'),c.identity_name_key('YWCA USA Foundation'))
        self.assertNotEqual(c.identity_name_key('YWCA Boston'),c.identity_name_key('YWCA USA'))
    def test_ca_checks_returned_ein(self):
        rows=[{'fein':'99-9999999','entityName':'Wrong Chapter','dba':'Wrong Alias'},
              {'fein':'13-1624103','legalName':'YWCA Legal','dba':'YWCA DBA','officer':'Not an Alias'}]
        with patch.object(c,'identity_fetch',return_value=json.dumps(rows).encode()):
            r=c.identity_ca_names(EIN,time.monotonic()+1)
        self.assertEqual([x['name'] for x in r['names']],['YWCA Legal','YWCA DBA'])
    def test_co_uses_live_rows_and_labels_historical(self):
        rows=[{'fein':'13-1624103','name':'New Name','entityid':'1'},
              {'fein':'13-1624103','name':'New Name Inc','entityid':'1'},
              {'fein':'13-1624103','name':'Former Name','entityid':'1'},
              {'fein':'99-9999999','name':'Wrong Name','entityid':'2'}]
        with patch.object(c,'identity_fetch',return_value=json.dumps(rows).encode()) as fetch:
            r=c.identity_co_names(EIN,time.monotonic()+1)
        self.assertIn('data.colorado.gov',fetch.call_args.args[0]);self.assertEqual(len(r['names']),2)
        self.assertFalse(r['names'][0]['historical']);self.assertTrue(r['names'][1]['historical'])
    def test_irs_only_header_and_explicit_dba(self):
        r=c.irs_header_evidence(header(dba='YWCA Public Name'),EIN,'https://source')
        self.assertEqual([x['name'] for x in r['names']],['YWCA USA INC','YWCA Public Name'])
        self.assertEqual(r['filing']['period_end'],'2025-06-30')
    def test_blank_dba_is_not_global_alias_absence(self):
        r=c.irs_header_evidence(header(),EIN,'https://source')
        self.assertFalse(r['dba_disclosed']);self.assertEqual(len(r['names']),1)
    def test_irs_wrong_ein_or_invalid_period_rejected(self):
        for source in [header(ein='999999999'),header(end='06-30-2028'),header(begin='bad')]:
            with self.assertRaises(ValueError): c.irs_header_evidence(source,EIN,'https://source')
    def test_stale_oregon_cannot_discover(self):
        with patch.object(c,'downloadable_data_info',return_value={'usable':False}),patch.object(c,'or_snapshot_row_dict_for_ein') as read:
            with self.assertRaises(ValueError): c.identity_or_names(EIN,time.monotonic()+1)
            read.assert_not_called()
    def test_cache_key_includes_ein_and_weekly_revision(self):
        with patch.object(c,'downloadable_data_info',return_value={'usable':True,'revision':1}) as info,patch.object(c,'identity_or_names',return_value={'names':[],'complete':True}) as fetch:
            c.identity_source_result('OR',EIN,time.monotonic()+1)
            self.assertTrue(c.identity_source_result('OR',EIN,time.monotonic()+1)['cache_hit'])
            c.identity_source_result('OR','840865803',time.monotonic()+1)
            info.return_value={'usable':True,'revision':2}
            c.identity_source_result('OR',EIN,time.monotonic()+1)
            self.assertEqual(fetch.call_count,3)
    def test_failed_source_partial_still_returns_other_names(self):
        def source(st,ein,deadline):
            if st=='CA':raise TimeoutError()
            return {'source':st,'complete':True,'names':[c.identity_candidate('YWCA USA Inc',st,'Legal','https://source')]}
        with patch.object(c,'identity_source_result',side_effect=source):r=c.discover_organization_names('YWCA',EIN)
        self.assertTrue(r['partial']);self.assertEqual(len(r['names']),1);self.assertNotIn('status',r)
    def test_server_deadline_does_not_wait_for_unfinished_workers(self):
        def source(st,ein,deadline):
            if st=='CA':time.sleep(.15)
            return {'source':st,'complete':True,'names':[]}
        with patch.object(c,'IDENTITY_DEADLINE_SECONDS',.03),patch.object(c,'identity_source_result',side_effect=source):
            start=time.monotonic();r=c.discover_organization_names('YWCA',EIN)
            self.assertLess(time.monotonic()-start,.12);self.assertTrue(r['partial'])
            time.sleep(.16)
    def test_reviewed_names_are_request_scoped_and_propagate(self):
        @c.reviewed_name_scope
        def lookup(orgs,states):
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                return c.submit_with_identity(pool,c.known_names_for_ein,orgs[0]['ein']).result()
        def run(name):return lookup([{'ein':EIN,'alternate_names':[name]}],[])
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,['Alias One','Alias Two']))
        self.assertEqual(results,[['Alias One'],['Alias Two']]);self.assertEqual(c.known_names_for_ein(EIN),[])
    def test_exact_reviewed_name_does_not_accept_other_ein_or_chapter(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('National Board of the YWCA of the USA',)})
        self.assertTrue(c.registry_name_is_safe_for_org('National Board of the YWCA of the USA','YWCA USA',EIN))
        self.assertFalse(c.registry_name_is_safe_for_org('YWCA Boston Chapter','YWCA USA',EIN))
        self.assertEqual(c.score_candidate('YWCA USA',EIN,{'name':'National Board of the YWCA of the USA','ein':'999999999'})['reason'],'REJECT_DIFFERENT_EIN')
        self.assertEqual(c.score_candidate('YWCA USA',EIN,{'name':'National Board of the YWCA of the USA'})['reason'],'MATCH_REVIEWED_ALTERNATE_NAME')
    def test_removed_names_not_reloaded_from_discovery_cache(self):
        c.IDENTITY_SOURCE_CACHE[(EIN,'CA','live-v1')]=(time.time()+100,{'names':[{'name':'Removed'}]})
        c.REVIEWED_NAME_CONTEXT.set({EIN:()});self.assertEqual(c.known_names_for_ein(EIN),[])
        self.assertNotIn('Removed',c.build_search_queries('YWCA USA',EIN,max_queries=6))
    def test_query_budget_and_original_preserved(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:('National Board of the YWCA of the USA','YWCA Public')})
        values=c.build_search_queries('YWCA USA',EIN,max_queries=4)
        self.assertEqual(values[:3],['YWCA USA','National Board of the YWCA of the USA','YWCA Public']);self.assertLessEqual(len(values),4)
        values=c.organization_name_variants('YWCA USA',EIN)
        self.assertEqual(values[:3],['YWCA USA','National Board of the YWCA of the USA','YWCA Public'])
    def test_invalid_ein_is_rejected_before_source_calls(self):
        with patch.object(c,'identity_source_result') as source:
            for ein in ['abc131624103','13162410','000000000']:
                with self.assertRaises(ValueError):c.discover_organization_names('YWCA',ein)
            source.assert_not_called()
    def test_ny_continuation_carries_only_reviewed_names(self):
        auth={'email':'qa@compliance-express.com','admin_passcode':c.ADMIN_PASSCODE,'device_id':'identity-test-device'}
        seen=[]
        def advance(record):
            seen.append(c.known_names_for_ein(EIN))
            record['pending']={'query_id':'q','query':{'ein':'13-1624103'}}
            return {'phase':'search',**record['pending']}
        with patch.object(c,'NY_CONNECTOR_SIGNING_KEY','x'*64),patch.object(c,'ny_connector_advance',side_effect=advance):
            code,response=c.ny_connector_request(dict(auth,action='start',organization_name='YWCA',ein='13-1624103',alternate_names=['Only reviewed']),c.NY_CONNECTOR_ORIGIN)
            self.assertEqual(code,200)
            record=c.ny_connector_unpack(response['check_token'],auth['email'],auth['device_id'])
            self.assertEqual(record['alternate_names'],['Only reviewed']);self.assertEqual(seen,[['Only reviewed']])
            self.assertEqual(c.known_names_for_ein(EIN),[])
    def test_normalization_distinguishes_omitted_from_reviewed_empty(self):
        with patch.object(c,'resolved_organization_name',return_value='Test'):
            base={'organization_name':'Test','ein':EIN}
            self.assertNotIn('alternate_names',c.normalize_organization_requests(base,True)[0])
            self.assertEqual(c.normalize_organization_requests(dict(base,alternate_names=[]),True)[0]['alternate_names'],[])
        for value in ['bad',[1],['a']*13,['bad\nname']]:
            with self.assertRaises(ValueError):c.normalize_reviewed_names(value)

if __name__=='__main__': unittest.main()
