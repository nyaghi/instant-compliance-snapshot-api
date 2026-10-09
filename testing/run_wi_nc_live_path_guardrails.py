"""No live requests: real WI parsers/search and NC query-bound continuations."""
import io
import ast
import json
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import registry_snapshot_server as c
from testing.run_final_four_source_guardrails import NC, NC_PROFILE


class WisconsinLivePath(unittest.TestCase):
    def row(self, name, kind='html', number='2151-800'):
        href='CredSummaryDetails.aspx?chid=12345'
        if kind=='html':
            values=[number,'Charitable Organization',f'<a href="{href}">{name}</a>',
                    'SACRAMENTO, CA','07/01/2000','07/31/2027']
            return '<tr>'+''.join(f'<td>{v}</td>' for v in values)+'</tr>'
        return f'| {number} | Charitable Organization | [{name}]({href}) | SACRAMENTO, CA | 07/01/2000 | 07/31/2027 |'

    def detail(self,name,number='2151-800'):
        return f'Name: {name} Credential Type: Charitable Organization Credential Number: {number} Location: SACRAMENTO, CA Status License is current (Active)'

    def parsed(self,entered,name,kind,detail=None,address='corroborated'):
        targets=c.organization_match_target_variants(entered,'680124097')
        parser=c.wi_candidate_from_row_html if kind=='html' else c.wi_candidate_from_markdown_row
        with patch.object(c,'wi_http_detail_text',return_value=detail if detail is not None else self.detail(name)), \
             patch.object(c,'wi_reader_text',return_value=detail if detail is not None else self.detail(name)), \
             patch.object(c,'registry_address_evidence',return_value={'decision':address}), \
             patch.object(c,'registry_cross_state_identity',return_value=None):
            return parser(self.row(name,kind),targets,entered,'680124097')

    def test_both_live_parsers_accept_full_supplied_components(self):
        for entered,name in [('United Animal Nations — RedRover','UNITED ANIMAL NATIONS'),
                             ('Beacon Literacy Network / ReadTogether','Beacon Literacy Network, Inc.'),
                             ('Harbor Animal Rescue - RescueBridge','RescueBridge')]:
            for kind in ['html','markdown']:
                with self.subTest(entered=entered,kind=kind):
                    candidate=self.parsed(entered,name,kind)
                    self.assertIsNotNone(candidate)
                    self.assertFalse(candidate['identity_conflict'])
                    self.assertEqual(candidate['primary_registry_name'],name)

    def test_complete_live_search_returns_status_without_snapshot(self):
        name='UNITED ANIMAL NATIONS'
        page='<table id="ctl00_cphMainContent_OrgCredentialSearch_gvCredentialSearchResults">'+self.row(name)+'</table>'
        opener=Mock();opener.open.side_effect=lambda *a,**kw:io.BytesIO(page.encode())
        with patch.object(c,'wi_request_opener',return_value=opener), \
             patch.object(c,'wi_http_detail_text',return_value=self.detail(name)), \
             patch.object(c,'registry_address_evidence',return_value={'decision':'corroborated'}), \
             patch.object(c,'wi_reader_text',side_effect=AssertionError('No extra reader needed')), \
             patch.object(c,'search_wi_snapshot',side_effect=AssertionError('Wrong lookup path')):
            result=c.search_wi(None,c.checker.Organization('United Animal Nations — RedRover','680124097'))
        self.assertTrue(result.success)
        self.assertEqual(result.status,'Current')
        self.assertEqual(result.matched_registry_identifier,'2151-800')

    def test_related_entities_and_institution_scope_still_fail(self):
        for entered,name in [('United Animal Nations — RedRover','United Animal Nations Foundation'),
                             ('Wild Ones - Natural Landscapers','Wild Ones Milwaukee Chapter'),
                             ('University of California - Los Angeles','University of California')]:
            for kind in ['html','markdown']:
                with self.subTest(entered=entered,kind=kind):
                    candidate=self.parsed(entered,name,kind)
                    self.assertTrue(candidate is None or candidate.get('identity_conflict'))

    def test_missing_wrong_credential_and_address_conflict_not_accepted(self):
        for kind in ['html','markdown']:
            for detail in ['',self.detail('UNITED ANIMAL NATIONS','999-800')]:
                self.assertTrue(self.parsed('United Animal Nations — RedRover','UNITED ANIMAL NATIONS',kind,detail)['identity_conflict'])
            self.assertTrue(self.parsed('United Animal Nations — RedRover','UNITED ANIMAL NATIONS',kind,address='different_ein')['identity_conflict'])


class NorthCarolinaPlanning(unittest.TestCase):
    def test_nc_completed_search_mode_passes_signed_evidence_boundary(self):
        query={'state':'NC','operation':'search','name':'Beacon Literacy'}
        base={'state':'NC','query':query,'complete':True,
              'verification_pending':False,'rows':[],'total':0}
        marked={**base,'search_mode':'STARTS_WITH'}
        self.assertEqual(c.final_four_clean_evidence(marked,query),marked)
        self.assertEqual(c.final_four_clean_evidence(base,query),base)
        for bad in ({**base,'search_mode':'EXACT_MATCH'},
                    {**base,'search_mode':'UNVERIFIED'},
                    {**marked,'complete':False}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                c.final_four_clean_evidence(bad,query)

    def run_lookup(self,name,aliases=(),address='corroborated',empty=False):
        calls=[]
        org=c.checker.Organization(name,'452894444')
        card={**NC,'CSL Legal Name':name}
        profile={**NC_PROFILE,'Name':name}
        def source(query):
            calls.append(query)
            if query['operation']=='detail':
                return {'query':query,'complete':True,'fields':profile}
            if not empty and query['name'] in {'Saving','Beacon'}:
                raise AssertionError('Unrelated broad query issued')
            rows=[] if empty or query['name']!=name else [card]
            return {'state':'NC','query':query,'complete':True,'verification_pending':False,'search_mode':'STARTS_WITH','rows':rows,'total':len(rows)}
        token=c.REVIEWED_NAME_CONTEXT.set({'452894444':tuple(aliases)})
        try:
            with patch.object(c,'trial_identity',return_value={'origin':'isolated'}), \
                 patch.object(c,'reconciled_registry_address',return_value={'decision':address,'ein_linked_location':'Roanoke, TX'}):
                result=c.final_four_browser_lookup(org,'NC',source)
            return result,calls
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_broad_query_skips_only_its_completed_full_name(self):
        for name,query in [('Saving Moses','Saving'),('Beacon Literacy Network','Beacon')]:
            row={'name':name,'identifier':'SL123','url':'https://www.sosnc.gov/profile','expiration':c.date(2027,1,1)}
            self.assertTrue(c.nc_redundant_broad_query(query,[name,'World Child'],[row]))
            self.assertFalse(c.nc_redundant_broad_query(query,[name,'World Child'],[]))
            for field in ['name','identifier','url','expiration']:
                broken=dict(row);broken.pop(field)
                self.assertFalse(c.nc_redundant_broad_query(query,[name,'World Child'],[broken]))

    def test_short_legal_name_and_punctuation_fallbacks_preserved(self):
        for name,query in [('Family','Family'),('World Child','World'),
                           ("America's Charities",'America Charities'),
                           ('Make-A-Wish Foundation','Make A Wish Foundation'),
                           ('Saving Moses','Saving Mos')]:
            row={'name':name,'identifier':'SL123','url':'https://www.sosnc.gov/profile','expiration':c.date(2027,1,1)}
            self.assertFalse(c.nc_redundant_broad_query(query,[name],[row]))

    def test_actual_plan_keeps_profile_and_review_without_broad_saving(self):
        result,calls=self.run_lookup('Saving Moses',['SAVING MOSES','World Child'],address='conflict')
        self.assertEqual(result.status,'Needs Review')
        self.assertIn('World Child',[q.get('name') for q in calls])
        self.assertIn('Saving Mos',[q.get('name') for q in calls])
        self.assertNotIn('Saving',[q.get('name') for q in calls])
        self.assertTrue(result._cc_identity_review['search_complete'])

    def test_known_positive_and_complete_no_record(self):
        result,_=self.run_lookup('Saving Moses')
        self.assertIn(result.status,{'Current','Upcoming Filing'})
        result,calls=self.run_lookup('Beacon Literacy Network',['Child Aid'],empty=True)
        self.assertEqual(result.status,'Not Registered')
        self.assertIn('Child Aid',[q.get('name') for q in calls])

    def test_completed_starting_with_covers_longer_reviewed_nc_name(self):
        org=c.checker.Organization('Beacon Literacy Network','452894444')
        cases=[
            (['Beacon Literacy','BEACON LITERACY NETWORK'], 'STARTS_WITH',
             ['Beacon Literacy']),
            (['Beacon Literacy','Beacon-Literacy Network'], 'STARTS_WITH',
             ['Beacon Literacy','Beacon-Literacy Network']),
            (['Beacon Literacy','Beacon Literacy Network'], 'EXACT_MATCH',
             ['Beacon Literacy','Beacon Literacy Network']),
        ]
        for required,first_mode,expected in cases:
            with self.subTest(required=required,first_mode=first_mode):
                calls=[]
                def source(query):
                    calls.append(query['name'])
                    return {'state':'NC','query':query,'complete':True,
                            'verification_pending':False,
                            'search_mode':first_mode if len(calls)==1 else 'STARTS_WITH',
                            'rows':[],'total':0}
                with patch.object(c,'trial_identity',return_value={'origin':'isolated'}), \
                     patch.object(c,'licensed_charity_names',return_value=(required,[])):
                    result=c.final_four_browser_lookup(org,'NC',source)
                self.assertEqual(calls,expected)
                self.assertEqual(result.status,'Not Registered')

    def test_incomplete_nc_prefix_cannot_cover_longer_name(self):
        org=c.checker.Organization('Beacon Literacy Network','452894444')
        calls=[]
        def source(query):
            calls.append(query['name'])
            return {'state':'NC','query':query,'complete':False,
                    'verification_pending':False,'search_mode':'STARTS_WITH',
                    'rows':[],'total':0}
        with patch.object(c,'trial_identity',return_value={'origin':'isolated'}), \
             patch.object(c,'licensed_charity_names',return_value=(
                 ['Beacon Literacy','Beacon Literacy Network'],[])):
            with self.assertRaises(ValueError):
                c.final_four_browser_lookup(org,'NC',source)
        self.assertEqual(calls,['Beacon Literacy'])

    def test_reported_nc_fourth_query_is_covered_without_state_exception(self):
        org=c.checker.Organization('American Indian/Alaska Native Tourism Association','450541654')
        reviewed=['American Indian','Alaska Native Tourism Association',
                  'AMERICAN INDIAN ALASKA NATIVE TOURISM ASSOCIATION, INC.',
                  'ALASKA NATIVE TOURISM ASSOCIATION, INC. (AIANTA)']
        calls=[]
        def source(query):
            calls.append(query['name'])
            if len(calls)==4:
                raise RuntimeError('simulated source rate limit')
            return {'state':'NC','query':query,'complete':True,
                    'verification_pending':False,'search_mode':'STARTS_WITH',
                    'rows':[],'total':0}
        with patch.object(c,'trial_identity',return_value={'origin':'isolated'}), \
             patch.object(c,'licensed_charity_names',return_value=(reviewed,[])):
            result=c.final_four_browser_lookup(org,'NC',source)
        self.assertEqual(calls,reviewed[:2])
        self.assertEqual(result.status,'Not Registered')
        self.assertIn({'reviewed_name_coverage':{'name':reviewed[2],
                       'completed_starts_with':reviewed[0]}},result.source_attempts)
        self.assertIn({'reviewed_name_coverage':{'name':reviewed[3],
                       'completed_starts_with':reviewed[1]}},result.source_attempts)

    def test_trial_connector_labels_only_fully_read_nc_starting_with_result(self):
        source=(Path(__file__).resolve().parents[1]/'browser-connector/registry-content.js').read_text()
        start=source.index('  async function ncRows(')
        end=source.index('  function ncProfile(',start)
        block=source[start:end]
        self.assertIn("searched=/Words:\\s*Starting With",block)
        self.assertIn("search_mode:'STARTS_WITH'",block)
        self.assertLess(block.index('if(rows.length!==total'),
                        block.index("search_mode:'STARTS_WITH'"))

    def test_trial_browser_asset_classifies_explicit_429_only(self):
        from deployment import performance_lab as lab
        root=Path(__file__).resolve().parents[1]
        with patch.object(lab,'trial_identity',return_value={'origin':'https://trial.invalid','label':'29.2CB'}):
            text=lab.final_four_asset('ny-connector.js',(root/'web-staging/ny-connector.js').read_text())
        start=text.index('        if (registryState === "NC" && completed.ok === false')
        block=text[start:text.index('        state = completed.ok',start)]
        tests=[('NC',False,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED',429,True,'NY_CONNECTOR_NC_RATE_LIMITED'),
               ('NC',False,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED',200,True,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED'),
               ('NC',True,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED',429,True,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED'),
               ('NY',False,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED',429,True,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED'),
               ('NC',False,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED',429,False,'NY_CONNECTOR_NC_SEARCH_NOT_STARTED'),
               ('NC',False,'NY_CONNECTOR_NC_VERIFICATION_PENDING',429,True,'NY_CONNECTOR_NC_VERIFICATION_PENDING')]
        script='const tests='+json.dumps(tests)+'; for(const [registryState,ok,reason,status,search_route,expected] of tests){let completed={ok,reason,nc_submission:[{requests:[{status,search_route}]}]};'+block+'if(completed.reason!==expected)throw Error(JSON.stringify(completed));}'
        node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        subprocess.run([str(node),'-e',script],check=True,capture_output=True)

    def test_scope_against_deployed_ca(self):
        root=Path(__file__).resolve().parents[1]
        old=ast.parse(subprocess.check_output(['git','show','24dcec600135151b6ad75f791cc9db70c7eaf1f5:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8-sig'))
        allowed={'final_four_browser_lookup','final_four_connector_failure','nc_redundant_broad_query',
                 'wi_live_candidate_name_is_safe','wi_candidate_from_row_html','wi_candidate_from_markdown_row'}
        for tree in [old,new]:
            tree.body=[n for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name not in allowed]
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_nc_rate_limit_does_not_trigger_fresh_page_recovery(self):
        from testing.run_final_four_continuation_guardrails import ContinuationControls
        control=ContinuationControls();control.setUp()
        try:
            _,pending=control.start('NC',recovery_protocol='nc-fresh-search-v1')
            code,result=control.request({'action':'fail','check_token':pending['check_token'],
                'query_id':pending['query_id'],'reason':'NY_CONNECTOR_NC_RATE_LIMITED'})
            self.assertEqual(code,200)
            self.assertEqual(result['phase'],'complete')
            self.assertNotIn('recovery',result)
            self.assertIn('HTTP 429',result['result']['comments'])
            self.assertNotEqual(result['result']['status'],'Not Registered')
        finally:control.doCleanups()


if __name__=='__main__':unittest.main()
