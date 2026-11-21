"""70 recorded organization inputs; synthetic source/identity edge conditions."""
import ast, copy, json, os, subprocess, sys, time, types, unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import registry_snapshot_server as cc

CASES = json.loads((ROOT/'testing/fixtures/gate54-state-controls.json').read_text())['cases']
old = subprocess.check_output(['git','show','8a5ad0b:registry_snapshot_server.py'],cwd=ROOT).decode('utf-8')
tree = ast.parse(old)
baseline = types.ModuleType('ri_sd_baseline')
baseline.__dict__.update(cc.__dict__)
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {'search_ri','ri_charity_search'}],type_ignores=[]),'baseline-ri','exec'),baseline.__dict__)

def row(case, identifier='CO.100', status='Current', **extras):
    return dict(name=case['name'],identifier=identifier,status=status,raw_status='ACTIVE',
                expiration=date.today()+timedelta(days=365),location='Boston, MA',ein=case['ein'],**extras)

def lookup(module, case, *, failure=None, outcome='accepted', status='Current', later=None, primary=True):
    org=cc.checker.Organization(case['name'],case['ein'])
    required=[case['name'],'BROAD ALIAS','REVIEWED FORMER NAME']
    rows={'C1':row(case,status=status)}
    calls=[]
    def search(query,*args):
        calls.append(query)
        if query==required[0]:return [{'id':'C1','title':case['name']}] if primary else []
        if query==required[1] and failure:raise failure
        if query==required[2] and later:
            rows['C2']=later
            return [{'id':'C2','title':later['name']}]
        return []
    def identity(org,r,*args):
        r['match']={'decision':outcome,'reason':'MATCH_EIN_EXACT','score':100}
        r['address_evidence']={'decision':'corroborated'}
        return outcome
    replacements=dict(registry_json_request=lambda *a,**k:{'access_token':'local-token'},
                      licensed_charity_names=lambda *a,**k:(required,[]),
                      ri_charity_search=search,ri_charity_detail=lambda candidate,*a:copy.deepcopy(rows[candidate['id']]))
    # Helpers retain their actual selectors/status logic; synthetic identity
    # outcomes isolate the source-completeness change without network access.
    with patch.dict(module.__dict__,replacements),patch.object(cc,'licensed_charity_identity',side_effect=identity),patch.object(cc,'score_candidate',return_value={'decision':'accepted'}),patch.object(cc,'log_error'):
        result=module.search_ri(org)
    return result,calls

class RiSecondarySearch(unittest.TestCase):
    def test_original_iona_payload_uses_real_parser_and_identity_guards(self):
        folder=ROOT/'testing/fixtures/gate54-iona-ri'
        candidates=json.loads((folder/'PUBLIC-IONA-UNIVERSITY.json').read_text())
        detail=json.loads((folder/'PUBLIC-DETAIL-C170837.json').read_text())
        seen=[]
        def request(url,*args,**kwargs):
            if url.endswith('/token'):return {'access_token':'local-token'}
            if url.endswith('/details'):return copy.deepcopy(detail)
            query=kwargs['payload']['formRequest']['values']['organizationName'];seen.append(query)
            return {'results':copy.deepcopy(candidates) if query=='IONA UNIVERSITY' else [],
                    'resultCount':1039 if query=='IONA' else len(candidates) if query=='IONA UNIVERSITY' else 0}
        token=cc.REVIEWED_NAME_CONTEXT.set({'133508093':['IONA UNIVERSITY','Iona College','IONA','IONA, IONA UNIVERSITY']})
        try:
            for address,expected in [('corroborated',True),('conflict',False)]:
                with patch.object(cc,'registry_json_request',side_effect=request),patch.object(cc,'reconciled_registry_address',return_value={'decision':address,'basis':'Recorded 715 North Avenue / New Rochelle NY office comparison'}),patch.object(cc,'licensed_charity_street_evidence',return_value={}),patch.object(cc,'log_error'):
                    result=cc.search_ri(cc.checker.Organization('IONA UNIVERSITY','133508093'))
                self.assertEqual(result.success,expected)
                if expected:
                    self.assertEqual(result.status,'Current')
                    self.assertEqual(result.matched_registry_identifier,'CO.9905404')
                    self.assertEqual(result.computed_due_date,'2027-10-02')
                    self.assertIn('IONA, IONA UNIVERSITY',seen)
        finally:cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_70_recorded_organizations_paired_and_guarded(self):
        self.assertEqual(len({c['ein'] for c in CASES}),70)
        observations=[]
        for case in CASES:
            with self.subTest(organization=case['name']):
                good,_=lookup(cc,case)
                oldgood,_=lookup(baseline,case)
                self.assertEqual((good.status,good.success,good.matched_registry_identifier),(oldgood.status,oldgood.success,oldgood.matched_registry_identifier))
                kept,calls=lookup(cc,case,failure=cc.RiSearchTooBroad('too broad'))
                oldbad,_=lookup(baseline,case,failure=cc.RiSearchTooBroad('too broad'))
                self.assertTrue(kept.success);self.assertEqual(kept.status,'Current')
                self.assertEqual(kept.matched_registry_identifier,'CO.100')
                self.assertIn('1,000-record',kept.source_note)
                self.assertFalse(oldbad.success)
                self.assertEqual(calls[-1],'REVIEWED FORMER NAME')
                for state in ['Current','Upcoming Filing','Exempt','Pending']:
                    r,_=lookup(cc,case,status=state,failure=cc.RiSearchTooBroad('too broad'))
                    self.assertTrue(r.success);self.assertEqual(r.status,state)
                for state in ['Closed / Withdrawn / Canceled','Delinquent','Revoked','Suspended']:
                    r,_=lookup(cc,case,status=state,failure=cc.RiSearchTooBroad('too broad'))
                    self.assertFalse(r.success)
                for identity in ['rejected','possible','conflict']:
                    # A conflicting source has its ordinary address metadata.
                    if identity=='conflict':continue
                    r,_=lookup(cc,case,outcome=identity,failure=cc.RiSearchTooBroad('too broad'))
                    self.assertFalse(r.success)
                for exc in [TimeoutError('source timeout'),ValueError('result count changed'),ValueError('malformed detail')]:
                    r,_=lookup(cc,case,failure=exc)
                    self.assertFalse(r.success)
                missing,_=lookup(cc,case,primary=False,failure=cc.RiSearchTooBroad('too broad'))
                self.assertFalse(missing.success)
                # All remaining required aliases are still searched; a newer
                # credential can supersede the original primary record.
                newer=row(case,'CO.200')
                newer['expiration']=date.today()+timedelta(days=700)
                r,_=lookup(cc,case,failure=cc.RiSearchTooBroad('too broad'),later=newer)
                self.assertEqual(r.matched_registry_identifier,'CO.200')
                observations.append({'name':case['name'],'ein':case['ein'],'healthy_paired':True,'broad_secondary_recovery':True,'source_and_identity_failures_preserved':True,'later_credential_retained':True})
        out=Path(os.environ.get('CC_GATE54_TEST_OUTPUT',str(ROOT)))
        out.mkdir(exist_ok=True,parents=True)
        (out/'RI-70-RESULTS.json').write_text(json.dumps({'passed':True,'scope':'70 recorded organization inputs; synthetic responses/edge cases, not live searches.','cases':observations},indent=2))

    def test_only_overbroad_is_typed_not_unstable_or_incomplete(self):
        deadline=time.monotonic()+10
        with patch.object(cc,'registry_json_request',return_value={'results':[],'resultCount':1039}):
            with self.assertRaises(cc.RiSearchTooBroad):cc.ri_charity_search('BROAD',deadline,{})
        for payload in [{'results':[]},{'results':[],'resultCount':1},{'results':[],'resultCount':0,'message':{'errors':['source error']}}]:
            with patch.object(cc,'registry_json_request',return_value=payload):
                with self.assertRaises(ValueError) as caught:cc.ri_charity_search('NAME',deadline,{})
                self.assertNotIsInstance(caught.exception,cc.RiSearchTooBroad)
        with patch.object(cc,'registry_json_request',side_effect=[{'results':[{'id':'C1','title':'Primary'}],'resultCount':2},{'results':[],'resultCount':3}]):
            with self.assertRaises(ValueError) as caught:cc.ri_charity_search('NAME',deadline,{})
            self.assertNotIsInstance(caught.exception,cc.RiSearchTooBroad)

if __name__=='__main__':unittest.main()
