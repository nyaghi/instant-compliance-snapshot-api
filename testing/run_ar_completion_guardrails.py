"""Arkansas empty-prefix completion; preserve complete identity matching."""
import sys, unittest, json
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode, urlparse, parse_qs
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

EIN='473272024'; NAME='Every Woman Treaty Inc.'
FORMER='INTERNATIONAL COMMISSION ON VIOLENCE AGAINST WOMEN AND GIRLS'
PREFIX='INTERNATIONAL COMMISSION ON'

class ArkansasCompletionTests(unittest.TestCase):
    def setUp(self):
        self.token=c.REVIEWED_NAME_CONTEXT.set({EIN:('EVERY WOMAN TREATY, INC.','Every Woman',FORMER)})
    def tearDown(self):c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def lookup(self, overrides=None, stale=False, aliases=None, name=None, seconds_per_query=0):
        if aliases is not None:c.REVIEWED_NAME_CONTEXT.set({EIN:tuple(aliases)})
        page=MagicMock(); submitted=[];query=[''];overrides=overrides or {}; elapsed=[0.0]
        def fill(value):
            if value:query[0]=value
        def click(**kwargs):
            submitted.append(query[0]);page.url=c.AR_SEARCH_URL+'?'+urlencode({'name':'Wrong Identity' if stale else query[0]})
            elapsed[0]+=seconds_per_query
        page.locator.return_value.fill.side_effect=fill
        page.get_by_role.return_value.click.side_effect=click
        page.goto.side_effect=lambda *a,**kw:setattr(page,'url',c.AR_SEARCH_URL)
        def body(p):
            if '?' not in p.url:return 'Name Search'
            return overrides.get(query[0],{}).get('body','Back to Search Form No Results Found')
        def rows(p):return overrides.get(query[0],{}).get('rows',[])
        clock=patch.object(c.time,'perf_counter',side_effect=lambda:elapsed[0]) if seconds_per_query else nullcontext()
        with clock,patch.object(c,'ar_wait_for_search_form',return_value=True),patch.object(c,'registry_page_body',side_effect=body),patch.object(c,'ar_result_rows',side_effect=rows),patch.object(c,'safe_wait_for_network_idle'):
            result=c.search_ar_precise(page,c.checker.Organization(name or NAME,EIN))
        return result,submitted
    def test_slow_multi_alias_lookup_reaches_primary_literal_before_aliases(self):
        name='Colorectal Cancer Alliance, Inc.'
        aliases=['COLORECTAL CANCER ALLIANCE, INC.','COLON CANCER ALLIANCE, INC.','UNDY 5000','Blue Note Fund','Stars Go Blue','CCA']
        row={'name':'Colorectal Cancer Alliance Inc.','status':'Current','type':'Charity','registration_date':'2011-04-05'}
        r,queries=self.lookup({'Colorectal Cancer Alliance':{'body':'Back to Search Form Registration Date','rows':[row]}},name=name,aliases=aliases,seconds_per_query=c.AR_NAME_SEARCH_MAX_SECONDS/7)
        self.assertEqual(r.status,'Current');self.assertEqual(r.matched_registry_name,row['name'])
        self.assertEqual(queries,[name,'Colorectal Cancer Alliance'])
    def test_primary_empty_punctuation_query_does_not_certify_timeout_negative(self):
        name='Example Wildlife Alliance, Inc.'
        r,queries=self.lookup(name=name,aliases=[name],seconds_per_query=c.AR_NAME_SEARCH_MAX_SECONDS)
        self.assertEqual(queries,[name]);self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)
    def test_alias_empty_punctuation_query_does_not_certify_timeout_negative(self):
        name='Example Wildlife Alliance';alias='Former Wildlife Charity, Inc.'
        r,queries=self.lookup(name=name,aliases=[alias],seconds_per_query=c.AR_NAME_SEARCH_MAX_SECONDS/2)
        self.assertEqual(queries,[name,alias]);self.assertEqual(r.status,'Unable to Verify');self.assertFalse(r.success)
    def test_no_alias_lookup_keeps_existing_early_literal_search(self):
        name='Example Wildlife Alliance, Inc.'
        r,queries=self.lookup(name=name,aliases=[],seconds_per_query=c.AR_NAME_SEARCH_MAX_SECONDS)
        self.assertEqual(queries,['Example Wildlife Alliance'])
        self.assertEqual(c.public_status(r),'Not Registered');self.assertTrue(r.success)
    def test_same_literal_query_can_certify_complete_no_record(self):
        name='Example Wildlife Alliance'
        r,_=self.lookup(name=name,aliases=[name],seconds_per_query=c.AR_NAME_SEARCH_MAX_SECONDS)
        self.assertEqual(c.public_status(r),'Not Registered');self.assertTrue(r.success)
    def test_late_primary_record_keeps_conflicting_ein_rejection(self):
        name='Example Wildlife Alliance, Inc.'
        row={'name':'Example Wildlife Alliance Inc.','ein':'999999999','status':'Current'}
        r,_=self.lookup({'Example Wildlife Alliance':{'body':'Back to Search Form Registration Date','rows':[row]}},name=name,aliases=[name])
        self.assertNotEqual(r.status,'Current');self.assertFalse(r.matched_registry_name)
    def test_literal_primary_does_not_accept_distinct_local_chapter(self):
        name='Example Wildlife Alliance, Inc.'
        row={'name':'Example Wildlife Alliance - Milwaukee Chapter','status':'Current'}
        r,_=self.lookup({'Example Wildlife Alliance':{'body':'Back to Search Form Registration Date','rows':[row]}},name=name,aliases=[name])
        self.assertNotEqual(r.status,'Current');self.assertFalse(r.matched_registry_name)
    def test_complete_former_name_still_searched_after_primary_literal(self):
        name='Example Wildlife Alliance, Inc.';alias='Former Wildlife Charity, Inc.'
        row={'name':alias,'status':'Current'}
        r,queries=self.lookup({alias:{'body':'Back to Search Form Registration Date','rows':[row]}},name=name,aliases=[alias])
        self.assertEqual(r.status,'Current');self.assertEqual(queries[:3],[name,'Example Wildlife Alliance',alias])
    def test_real_case_completes_without_full_name_or_covered_punctuation_retries(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/ar-empty-prefix-pages.json').read_text(encoding='utf-8'))
        observed={parse_qs(urlparse(p['url']).query)['name'][0]:{'body':p['body']} for p in fixture['pages']}
        self.assertEqual(len(observed),3)
        r,queries=self.lookup(observed)
        self.assertEqual(queries,[NAME,'Every Woman Treaty','Every Woman',PREFIX,'Every-Woman Treaty','Treaty']);self.assertEqual(c.public_status(r),'Not Registered');self.assertTrue(r.success)
        self.assertEqual(r.queries_completed,queries)
    def test_empty_suffixed_search_does_not_skip_shorter_or_comma_spelling(self):
        global NAME
        original=NAME
        try:
            NAME='Christian Research Institute Inc.'
            row={'name':'Christian Research Institute, Inc.','status':'Close','type':'Charity','registration_date':'1998-01-01'}
            r,queries=self.lookup({'Christian Research Institute':{'body':'Back to Search Form Registration Date','rows':[]},'CHRISTIAN RESEARCH INSTITUTE, INC.':{'body':'Back to Search Form Registration Date','rows':[row]}},aliases=['CHRISTIAN RESEARCH INSTITUTE, INC.'])
            self.assertIn('CHRISTIAN RESEARCH INSTITUTE, INC.',queries)
            self.assertEqual(c.public_status(r),'Closed / Withdrawn / Canceled')
        finally:NAME=original
    def test_record_without_inc_remains_retrievable_after_empty_suffixed_spellings(self):
        global NAME
        original=NAME
        try:
            NAME='Christian Research Institute Inc.'
            row={'name':'Christian Research Institute','status':'Close','type':'Charity','registration_date':'1998-01-01'}
            r,queries=self.lookup({'Christian Research Institute':{'body':'Back to Search Form Registration Date','rows':[row]}},aliases=['CHRISTIAN RESEARCH INSTITUTE, INC.'])
            self.assertIn('Christian Research Institute',queries)
            self.assertEqual(c.public_status(r),'Closed / Withdrawn / Canceled')
        finally:NAME=original
    def test_empty_shorter_reviewed_name_covers_its_skipped_longer_spelling(self):
        r,queries=self.lookup(aliases=['Every Woman', 'Every Woman Treaty International'])
        self.assertNotIn('Every Woman Treaty International',queries)
        self.assertEqual(c.public_status(r),'Not Registered')
    def test_empty_longer_spelling_never_covers_a_shorter_required_identity(self):
        values=c.ar_completed_empty_identities(['Institute Inc.'],{},['Institute'])
        self.assertNotIn('Institute',values)
    def test_prefix_is_not_an_accepted_identity(self):
        self.assertNotIn(PREFIX,c.organization_match_target_variants(NAME,EIN))
    def test_blocked_prefix_cannot_certify_negative(self):
        r,_=self.lookup({PREFIX:{'body':'403 ERROR Request blocked'}})
        self.assertEqual(r.status,'Site Not Reachable');self.assertFalse(r.success)
        self.assertEqual(r.queries_attempted,[NAME,'Every Woman Treaty','Every Woman',PREFIX])
    def test_incomplete_prefix_and_full_identity_cannot_certify_negative(self):
        r,_=self.lookup({PREFIX:{'body':'Back to Search Form Registration Date'},FORMER:{'body':'Back to Search Form Registration Date'}})
        self.assertEqual(r.status,'Unable to Verify');self.assertIn(FORMER,r.source_note)
        self.assertNotIn('did not expose stable result rows',r.raw_status_text)
    def test_empty_page_for_wrong_query_does_not_credit_prefix(self):
        r,queries=self.lookup(stale=True)
        self.assertIn(FORMER,queries) # No shortcut from a stale prefix response.
    def test_nonempty_unrelated_prefix_requires_full_identity_query(self):
        row={'name':'Unrelated Organization','status':'Current','type':'Charity','registration_date':'2020-01-01'}
        r,queries=self.lookup({PREFIX:{'body':'Back to Search Form Registration Date','rows':[row]}})
        self.assertIn(FORMER,queries);self.assertEqual(c.public_status(r),'Not Registered')
    def test_conflicting_ein_cannot_be_accepted_by_prefix(self):
        row={'name':FORMER,'ein':'999999999','status':'Current'}
        r,_=self.lookup({PREFIX:{'body':'Back to Search Form Registration Date','rows':[row]}})
        self.assertFalse(r.matched_registry_name);self.assertNotEqual(r.status,'Current')
    def test_full_former_identity_can_match_from_short_query(self):
        row={'name':FORMER,'status':'Current','type':'Charity','registration_date':'2020-01-01'}
        r,queries=self.lookup({PREFIX:{'body':'Back to Search Form Registration Date','rows':[row]}})
        self.assertEqual(r.status,'Current');self.assertEqual(r.matched_registry_name,FORMER)
    def test_different_reviewed_identity_cannot_be_omitted(self):
        extra='Another Distinct Charity'
        r,queries=self.lookup({extra:{'body':'403 ERROR'}},aliases=['Every Woman',FORMER,extra])
        self.assertIn(extra,queries);self.assertEqual(r.status,'Site Not Reachable')
    def test_literal_punctuation_is_preserved(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:("O'Brien Wildlife Rescue International Foundation",)})
        q,p=c.ar_reviewed_search_plan(c.checker.Organization(NAME,EIN),[])
        self.assertIn("O'Brien Wildlife Rescue",q)
        self.assertNotIn('obrien wildlife rescue',p)
    def test_no_reviewed_names_keep_original_plan_and_limit(self):
        c.REVIEWED_NAME_CONTEXT.set({EIN:()});generated=[f'Query {i}' for i in range(20)]
        q,p=c.ar_reviewed_search_plan(c.checker.Organization(NAME,EIN),generated)
        self.assertEqual(q,generated[:c.AR_NAME_SEARCH_MAX_VARIANTS]);self.assertEqual(p,{})
    def test_generic_or_nonliteral_prefix_never_gets_completion_credit(self):
        with patch.object(c,'reviewed_name_search_probes',return_value=[(FORMER,'Different Prefix'),(FORMER,'INTERNATIONAL_%')]):
            _,p=c.ar_reviewed_search_plan(c.checker.Organization(NAME,EIN),[])
            self.assertNotIn('different prefix',p);self.assertNotIn('international_%',p)
            self.assertEqual(p,{'every woman treaty':[NAME,'EVERY WOMAN TREATY, INC.']})

if __name__=='__main__':unittest.main(verbosity=2)
