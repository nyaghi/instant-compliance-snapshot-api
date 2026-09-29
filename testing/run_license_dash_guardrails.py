"""Punctuation retrieval controls: preserve full identity, budgets and other plans."""
import ast, json, subprocess, sys, time, unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import registry_snapshot_server as cc
from testing.run_il_ga_guardrails import ga_html
from testing.performance_origin_audit import RestoreApprovedOrigin

BASE='1ba90bd560af7121588b5f48c4e39216f174956b'
def old_plan(org):
    tree=ast.parse(subprocess.check_output(['git','show',BASE+':registry_snapshot_server.py'],cwd=ROOT,text=True,encoding='utf-8'))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='licensed_charity_names')
    context=dict(vars(cc));exec(compile(ast.Module(body=[fn],type_ignores=[]),'<prior-plan>','exec'),context)
    return context['licensed_charity_names'](org)

class DashControls(unittest.TestCase):
    def setUp(self):
        self.org=cc.checker.Organization('Wild Ones — Natural Landscapers','391695443')
        token=cc.REVIEWED_NAME_CONTEXT.set({'391695443':['WILD ONES -- NATURAL LANDSCAPERS, LTD.']})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset,token)
    def test_both_source_spellings_reachable_with_existing_budget(self):
        required,generated=cc.licensed_charity_names(self.org)
        self.assertEqual(required,[self.org.organization_name,'WILD ONES -- NATURAL LANDSCAPERS, LTD.'])
        self.assertIn('Wild Ones - Natural Landscapers',generated)
        self.assertIn('Wild Ones',generated)
        self.assertLessEqual(len(generated),3*len(required))
        self.assertLess(generated.index('Wild Ones'),generated.index('Wild Ones Natural Landscaper'))
    def test_ri_official_literal_search_shape(self):
        attempts=[]
        raw={'id':'C149478','title':'Wild Ones - Natural Landscapers, Ltd.'}
        def search(query,*args):
            attempts.append(query)
            return [raw] if query.casefold() in ['wild ones','wild ones - natural landscapers'] else []
        row={'name':raw['title'],'identifier':'CO.9904011','status':'Upcoming Filing','raw_status':'ACTIVE',
             'expiration':date(2027,1,13),'location':'Neenah, WI','initial':date(2022,1,13),'initial_label':'Initial Credential Date','url':'https://ridbrprod-search.state-reg-eastern.tylerapp.com/search/C149478/detail'}
        with patch.object(cc,'registry_json_request',return_value={'access_token':'fixture'}),patch.object(cc,'ri_charity_search',side_effect=search),patch.object(cc,'ri_charity_detail',return_value=row),patch.object(cc,'reconciled_registry_address',return_value={'decision':'corroborated','basis':'Fixture same-EIN location'}):
            result=cc.search_ri(self.org)
        self.assertEqual(result.status,'Upcoming Filing');self.assertEqual(result.matched_registry_identifier,'CO.9904011')
        self.assertTrue(any(q in attempts for q in ['Wild Ones','Wild Ones - Natural Landscapers']))
    def test_ga_complete_prefix_search_then_detail_identity(self):
        attempts=[]
        def evidence(query):
            attempts.append(query)
            if 'orgName' in query:
                return {'rows':[{'name':'Wild Ones--Natural Landscapers, Ltd','identifier':'CH016436','detail_key':'FIXTUREKEY','location':''}] if query['orgName'].casefold()=='wild ones' else []}
            return {'body':ga_html(full_name='Wild Ones--Natural Landscapers, Ltd',license_no='CH016436',expiry='2/10/2028')}
        with patch.object(cc,'reconciled_registry_address',return_value={'decision':'corroborated','basis':'Fixture same-EIN location'}):
            result=cc.il_ga_browser_lookup(self.org,'GA',evidence)
        self.assertEqual(result.status,'Current');self.assertEqual(result.matched_registry_identifier,'CH016436')
    def test_prefix_never_becomes_an_accepted_identity(self):
        for name in ['Wild Ones Milwaukee Chapter','Wild Ones Madison','Wild Ones Natural Landscaping Services LLC','Wild Ones']:
            self.assertNotEqual(cc.score_candidate(self.org.organization_name,self.org.ein,{'name':name})['decision'],'accepted',name)
        self.assertEqual(cc.score_candidate(self.org.organization_name,self.org.ein,{'name':'Wild Ones - Natural Landscapers, Ltd.','ein':'123456789'})['reason'],'REJECT_DIFFERENT_EIN')
        self.assertNotIn('Wild Ones',cc.organization_match_target_variants(self.org.organization_name,self.org.ein))
    def test_incomplete_prefix_search_never_negative(self):
        def evidence(query):
            if query.get('orgName')=='Wild Ones':raise TimeoutError('Incomplete source response')
            return {'rows':[]}
        with self.assertRaises(TimeoutError):cc.il_ga_browser_lookup(self.org,'GA',evidence)
    def test_unicode_double_dash_and_spacing_variants(self):
        for mark in ['—','–','‑','--',' - ',' -- ']:
            org=cc.checker.Organization('Beacon Learning'+mark+'Youth Network','123456789')
            required,generated=cc.licensed_charity_names(org)
            self.assertIn('Beacon Learning',generated,mark)
            self.assertLessEqual(len(generated),3*len(required))
    def test_no_unrelated_plans_change(self):
        for name in ["Trust for America’s Health",'Foundation for Food & Agriculture Research','Ceres, Inc.','Reading Is Fundamental, Inc. (RIF)','YWCA USA, Inc.','First Responders Children’s Foundation','The Dressage Foundation, Inc.','Momentum Unlimited, Inc.','Earthjustice','Make-A-Wish Foundation of America','Warrior-Scholar Project Foundation']:
            org=cc.checker.Organization(name,'123456789')
            self.assertEqual(cc.licensed_charity_names(org),old_plan(org),name)
    def test_no_generic_prefix_or_new_identity_scope(self):
        org=cc.checker.Organization('The Foundation — Youth Services','123456789')
        _,generated=cc.licensed_charity_names(org)
        self.assertNotIn('The Foundation',generated)
        self.assertEqual(cc.score_candidate('Beacon Learning — Youth Network','123456789',{'name':'Beacon Learning — Another Chapter'})['decision'],'rejected')
    def test_every_existing_master_function_except_query_plan_unchanged(self):
        previous=subprocess.check_output(['git','show',BASE+':registry_snapshot_server.py'],cwd=ROOT,text=True,encoding='utf-8')
        def functions(source):
            return {n.name:ast.dump(n,include_attributes=False) for n in RestoreApprovedOrigin().visit(ast.parse(source)).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        old=functions(previous);new=functions((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        self.assertEqual({name for name,body in old.items() if new.get(name)!=body},{'licensed_charity_names'})

if __name__=='__main__':unittest.main()
