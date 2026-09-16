"""Former-name discovery and Arkansas retrieval/identity boundaries."""
import json, sys, time, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
EIN='131624103'; ORIGINAL='YWCA USA, Inc.'
FORMER="Young Women's Christian Association of the United States of America Inc"
NATIONAL="Young Women's Christian Association of the United"
GENERIC="Young Women's Christian Association, Inc."

def historical(name=FORMER,ein=EIN,legacy=False):
    path='Name[1]/BusinessNameLine1[1]' if legacy else 'BusinessName[1]/BusinessNameLine1Txt[1]'
    return f'<span id="/AppData/SubmissionHeaderAndDocument/ReturnHeader[1]/Filer[1]/EIN[1]">{ein}</span><span id="/AppData/SubmissionHeaderAndDocument/ReturnHeader[1]/Filer[1]/{path}">{name}</span><span id="/AppData/SubmissionHeaderAndDocument/SubmissionDocument/IRS990ScheduleI[1]/RecipientBusinessName[1]">Wrong Affiliate</span>'

class FormerNameTests(unittest.TestCase):
    def test_actual_ywca_filer_discloses_full_former_name(self):
        source=(Path(__file__).parent/'fixtures/irs-header-formats/ywca-historical-filer.html').read_text(encoding='utf-8')
        self.assertEqual(c.irs_historical_filer_names(source,EIN,'https://source')[0]['name'],FORMER)
    def test_header_identity_is_independent_of_tax_period_parsing(self):
        for legacy in [False,True]:
            r=c.irs_historical_filer_names(historical(legacy=legacy),EIN,'https://source')
            self.assertEqual([x['name'] for x in r],[FORMER]);self.assertTrue(r[0]['historical'])
            self.assertTrue(r[0]['verified']);self.assertEqual(r[0]['evidence'][0]['url'],'https://source')
    def test_other_ein_or_missing_ein_cannot_supply_names(self):
        for ein in ['999999999','']:
            with self.assertRaises(ValueError):c.irs_historical_filer_names(historical(ein=ein),EIN,'https://source')
    def test_only_filer_name_not_schedule_or_careof(self):
        source=historical(name='')+'<span id="/AppData/SubmissionHeaderAndDocument/ReturnHeader[1]/Filer[1]/InCareOfNm[1]">Wrong Agent</span>'
        self.assertEqual(c.irs_historical_filer_names(source,EIN,'https://source'),[])
    def test_history_is_bounded_and_index_ein_specific(self):
        ids=['201420529349300312','201640639349300129','201810569349300251','201910729349300646']
        index=''.join(f'<a href="/nonprofits/organizations/{EIN}/{oid}/full">Filing</a>' for oid in reversed(ids))
        index+='<a href="/nonprofits/organizations/999999999/201320529349300312/full">Wrong EIN</a>'
        with patch.object(c,'identity_fetch',side_effect=[index.encode()]+[historical().encode()]*3) as fetch:
            r=c.identity_irs_historical_names(EIN,'202640859349301609',time.monotonic()+10)
            self.assertEqual(fetch.call_count,4);self.assertTrue(r['historical_complete'])
            self.assertEqual(r['historical_returns_checked'],3)
            self.assertIn(ids[0],fetch.call_args_list[1].args[0]);self.assertNotIn('2013',str(fetch.call_args_list))
    def test_history_failure_preserves_verified_latest_names_and_period(self):
        payload={'organization':{'ein':EIN,'name':ORIGINAL,'latest_object_id':'202640859349301609'}}
        evidence={'names':[c.identity_candidate(ORIGINAL,'IRS','Legal','https://source')],'filing':{'period_end':'2025-06-30'},'dba_disclosed':False}
        with patch.object(c,'identity_fetch',return_value=json.dumps(payload).encode()),patch.object(c,'irs_return_header',return_value=evidence),patch.object(c,'identity_irs_historical_names',side_effect=TimeoutError):
            r=c.identity_irs_names(EIN,time.monotonic()+1)
        self.assertFalse(r['complete']);self.assertFalse(r['historical_complete']);self.assertEqual(r['filing']['period_end'],'2025-06-30')
        self.assertEqual({x['name'] for x in r['names']},{ORIGINAL})

class ArkansasTests(unittest.TestCase):
    def setUp(self):self.token=c.REVIEWED_NAME_CONTEXT.set({EIN:('YWCA OF THE U.S.A. NATIONAL BOARD','YWCA OF THE U.S.A.','National Board of the YWCA of the USA',FORMER)})
    def tearDown(self):c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def decision(self,name,ein=''):
        return c.ar_candidate_identity({'name':name,'ein':ein},ORIGINAL,c.organization_match_target_variants(ORIGINAL,EIN),EIN)
    def lookup(self,rows,queries=None):
        with patch.object(c,'ar_preferred_name_variants',return_value=queries or ["Young Women's Christian"]),patch.object(c,'ar_wait_for_search_form',return_value=True),patch.object(c,'registry_page_body',return_value='Back to Search Form Registration Date'),patch.object(c,'safe_wait_for_network_idle'),patch.object(c,'ar_result_rows',return_value=rows):
            return c.search_ar_precise(Mock(),c.checker.Organization(ORIGINAL,EIN))
    def test_national_retained_generic_and_other_locations_rejected(self):
        self.assertEqual(self.decision(NATIONAL),'accept')
        for name in [GENERIC,"Young Men's and Young Women's Hebrew Associations","Young Women's Christian Association of Boston","Young Women's Christian Association of Greater Los Angeles",'YWCA Boston Chapter',"Young Women's Christian"]:
            with self.subTest(name=name):self.assertEqual(self.decision(name),'reject')
    def test_contradictory_ein_rejected_even_on_exact_name(self):
        for name in [ORIGINAL,FORMER,NATIONAL]:self.assertEqual(self.decision(name,'999999999'),'reject')
        self.assertEqual(self.decision('Different Former Name',EIN),'accept')
    def test_query_phrase_is_early_but_not_an_accepted_alias(self):
        variants=c.ar_preferred_name_variants(c.checker.Organization(ORIGINAL,EIN))
        self.assertEqual(variants[:3],[ORIGINAL,FORMER,"Young Women's Christian"])
        self.assertNotIn("Young Women's Christian",c.organization_match_target_variants(ORIGINAL,EIN))
        self.assertEqual(c.AR_NAME_SEARCH_MAX_VARIANTS,8)
    def test_generic_current_cannot_beat_national_not_current(self):
        national={'name':NATIONAL,'status':'Not Current','registration_date':'1998-03-23'}
        generic={'name':GENERIC,'status':'Current','registration_date':'2026-09-15'}
        for rows in [[generic,national],[national,generic]]:
            r=self.lookup(rows);self.assertEqual(r.matched_registry_name,NATIONAL);self.assertEqual(r.status,'Delinquent')
    def test_equal_national_identity_prefers_current_in_either_order(self):
        rows=[{'name':NATIONAL,'status':s,'registration_date':'1998-03-23'} for s in ['Current','Not Current']]
        for values in [rows,list(reversed(rows))]:self.assertEqual(self.lookup(values).status,'Current')
    def test_retrieval_probe_cannot_promote_generic_row(self):
        r=self.lookup([{'name':GENERIC,'status':'Current'}]);self.assertEqual(c.public_status(r),'Not Registered')
    def test_removed_alias_is_not_rediscovered_during_search(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:()})
        self.assertEqual(self.decision(NATIONAL),'reject')
        self.assertNotIn("Young Women's Christian",c.ar_preferred_name_variants(c.checker.Organization(ORIGINAL,EIN)))
    def test_exact_distinctive_names_control_group(self):
        for name in ['Make-A-Wish Foundation of America','America SCORES','Aeon','Earthjustice','Reading Is Fundamental','Call to Action','Good Sports, Inc.','FoodCorps','Autism Research Institute','American Public Gardens Association','Opportunity@Work','Eckerd Youth Alternatives, Inc.','Beth Israel Deaconess Hospital - Milton','End Violence Against Women International','American Farriers Association Foundation','Childrens Health Care Foundation','Christian Research Institute Inc.','Classical 98.1','Education Forward DC','YWCA Boston Chapter']:
            with self.subTest(name=name):
                targets=c.organization_match_target_variants(name,'012345678')
                self.assertEqual(c.ar_candidate_identity({'name':name},name,targets,'012345678'),'accept')
                self.assertEqual(c.ar_candidate_identity({'name':name,'ein':'999999999'},name,targets,'012345678'),'reject')
    def test_thirty_previously_observed_arkansas_controls(self):
        cases=json.loads((Path(__file__).parent/'fixtures/ar-recorded-control-rows.json').read_text(encoding='utf-8'))
        self.assertEqual(len(cases),30)
        for case in cases:
            with self.subTest(name=case['name']):
                c.REVIEWED_NAME_CONTEXT.set({c.canonical_ein_digits(case['ein']):tuple(case['alternate_names'])})
                org=c.checker.Organization(case['name'],case['ein'])
                with patch.object(c,'ar_preferred_name_variants',return_value=[org.organization_name]),patch.object(c,'ar_wait_for_search_form',return_value=True),patch.object(c,'registry_page_body',return_value='Back to Search Form Registration Date' if case['observed_rows'] else 'No Results Found'),patch.object(c,'safe_wait_for_network_idle'),patch.object(c,'ar_result_rows',return_value=case['observed_rows']):
                    result=c.search_ar_precise(Mock(),org)
                self.assertEqual(c.public_status(result),case['expected'])

if __name__=='__main__':unittest.main(verbosity=2)
