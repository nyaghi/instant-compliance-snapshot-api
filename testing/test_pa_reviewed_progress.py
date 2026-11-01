"""Same literal PA plan and bounded completed-progress reserve; no network."""
import ast,copy,json,subprocess,time,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as c
from deployment.state_snapshots import DEADLINE
ROOT=Path(__file__).resolve().parents[1]
WILLIAM=json.loads((ROOT/'testing/fixtures/pa-william-frozen.json').read_text())
class ProgressPlan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source=subprocess.check_output(['git','show','6c914e109caf5890cbed6f4d14a8ab0e923c6e71:registry_snapshot_server.py'],cwd=ROOT,text=True,encoding='utf-8')
        ns=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef)and n.name in ['pa_name_search_plan','search_pa_with_name_fallback_core']]
        cls.original=compile(ast.Module(body=ns,type_ignores=[]),'exact-MV-PA-functions','exec')
    def old(self):
        scope=dict(vars(c));exec(self.original,scope);return scope
    def requests(self,plan):
        done=[]
        for name in plan:
            if not any(other.casefold()in name.casefold()for other in done):done.append(name)
        return done
    def test_frozen_william_plan_keeps_every_literal_and_reduces_redundant_requests(self):
        org=c.checker.Organization(WILLIAM['name'],WILLIAM['ein'])
        with patch.object(c,'known_names_for_ein',return_value=WILLIAM['aliases']),patch.object(c,'trial_identity',return_value={'origin':'local'}):
            old=self.old()['pa_name_search_plan'](org);new=c.pa_name_search_plan(org)
        self.assertEqual(set(old),set(new));self.assertEqual(len(old),len(new));self.assertLessEqual(len(new),10)
        self.assertEqual(new[0],'WILLIAM & MARY ALUMNI ASSN');self.assertEqual(len(self.requests(old)),9);self.assertEqual(len(self.requests(new)),7)
        for name in old:self.assertTrue(any(q.casefold()in name.casefold()for q in self.requests(new)))
        self.assertIn('William and Mary Alumni Association',new)
    def test_thirty_retained_plans_keep_same_bounded_terms_and_nontrial_sales_order(self):
        cohort=json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text())[:30]
        for row in cohort:
            org=c.checker.Organization(row['name'],row['ein']);aliases=[row['name'],row['registry_name'],'Distinct Reviewed Campaign']
            with patch.object(c,'known_names_for_ein',return_value=aliases),patch.object(c,'trial_identity',return_value={'origin':'local'}):
                old=self.old()['pa_name_search_plan'](org);new=c.pa_name_search_plan(org);self.assertEqual(set(new),set(old));self.assertEqual(len(new),len(old))
                mode=c.LAB_LOOKUP_MODE_CONTEXT.set('sales')
                try:self.assertEqual(c.pa_name_search_plan(org),old)
                finally:c.LAB_LOOKUP_MODE_CONTEXT.reset(mode)
            with patch.object(c,'known_names_for_ein',return_value=aliases),patch.object(c,'trial_identity',return_value=None):
                self.assertEqual(c.pa_name_search_plan(org),self.old()['pa_name_search_plan'](org))
    def run_model(self,*,baseline=False,trial=True,mode='standard',parent=100,durations=None,fail_index=None,malformed=False):
        org=c.checker.Organization('Progress Control Foundation','123456789');plan=['Reviewed Alpha','Reviewed Beta','Reviewed Gamma','Reviewed Delta','Reviewed Epsilon','Reviewed Zeta','Reviewed Eta'];clock=[0.0];calls=[]
        initial=c.checker.StateResult(org.organization_name,org.ein,'PA','Not Registered','https://state');initial.success=True
        def fetch(url,deadline,**kw):
            query=json.loads(kw['data'])['EntityName'];calls.append({'query':query,'deadline':deadline,'started':clock[0]})
            duration=(durations or [2.4]*7)[len(calls)-1]
            if clock[0]+duration>=deadline:clock[0]=deadline;raise TimeoutError('modeled source allowance reached')
            clock[0]+=duration
            if fail_index==len(calls):
                if malformed:return b'{"Table":[],"Table1":[{"RESULTCOUNT":1}]}'
                failure=urllib.error.HTTPError(url,429,'source limit',{},None);failure.close();raise failure
            return b'{"Table":[],"Table1":[{"RESULTCOUNT":0}]}'
        token=DEADLINE.set(parent);mt=c.LAB_LOOKUP_MODE_CONTEXT.set(mode)
        try:
            with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.checker,'search_pa',return_value=initial),patch.object(c,'pa_name_search_plan',return_value=plan),patch.object(c,'identity_fetch',side_effect=fetch),patch.object(c,'trial_identity',return_value={'origin':'local'}if trial else None):
                scope=self.old()if baseline else None
                if baseline:scope['pa_name_search_plan']=lambda org:plan
                result=(scope['search_pa_with_name_fallback_core']if baseline else c.search_pa_with_name_fallback_core)(None,org,lambda r:r)
                result=c.pa_guard_search_completion(result,org,[{'step':'search','ein':'123456789','complete':True,'http_status':200,'row_eins':[]},*getattr(result,'_pa_api_attempts',[])])
        finally:DEADLINE.reset(token);c.LAB_LOOKUP_MODE_CONTEXT.reset(mt)
        return result,calls,clock[0]
    def test_one_reserve_finishes_completed_progress_with_original_parent_bound(self):
        old,_,oldseconds=self.run_model(baseline=True);new,calls,newseconds=self.run_model()
        self.assertEqual(old.reason_code,'PA_NAME_BUDGET_EXHAUSTED');self.assertEqual(new.status,'Not Registered');self.assertTrue(new.success)
        self.assertEqual(len(calls),7);self.assertAlmostEqual(newseconds,16.8);self.assertEqual(max(x['deadline']for x in calls),20)
        self.assertEqual(sum('progress_reserve_seconds'in a for a in new._pa_api_attempts),1)
        self.assertTrue(all(a['complete']for a in new._pa_api_attempts))
    def test_nontrial_sales_and_parent_cutoff_cannot_take_extra_time(self):
        for kw in [{'trial':False},{'mode':'sales'},{'parent':16}]:
            result,calls,seconds=self.run_model(**kw);self.assertFalse(result.success);self.assertEqual(result.reason_code,'PA_NAME_BUDGET_EXHAUSTED');self.assertLessEqual(max(x['deadline']for x in calls),15)
    def test_failed_or_truncated_progress_cannot_earn_reserve_or_negative(self):
        for kw in [{'fail_index':3},{'fail_index':3,'malformed':True},{'durations':[7,7,7,7,7,7,7]}]:
            result,calls,_=self.run_model(**kw);self.assertFalse(result.success);self.assertNotEqual(result.status,'Not Registered');self.assertLessEqual(max(x['deadline']for x in calls),15)
    def test_fast_completed_plan_has_same_queries_and_no_reserve(self):
        old,oldcalls,oldseconds=self.run_model(baseline=True,durations=[.1]*7);new,calls,seconds=self.run_model(durations=[.1]*7)
        self.assertEqual((new.status,new.success),(old.status,old.success));self.assertEqual(calls,oldcalls);self.assertAlmostEqual(seconds,oldseconds);self.assertFalse(any('progress_reserve_seconds'in a for a in new._pa_api_attempts))
if __name__=='__main__':unittest.main()
