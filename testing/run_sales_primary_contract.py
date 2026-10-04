"""Approved trial Sales contract, executed against the actual assembled UI."""
import ast
import json
import subprocess
import types
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

import registry_snapshot_server as cc
from deployment import durable_queue as dq, lab_identity, performance_lab as lab, queue_engine, staging_workflows
from testing.run_final_four_trial_workflow_guardrails import ROOT, NODE, TRIAL


def restore_primary_sales_scope(tree):
    """Strip only the two approved input guards for whole-master preservation."""
    ny=ast.parse('if trial_identity() and purpose == "registration" and payload.get("mode") == "sales":\n record["alternate_names"] = []').body[0]
    old=ast.parse('payload.get("alternate_names", [])',mode='eval').body
    new=ast.parse('[] if mode == "sales" else payload.get("alternate_names", [])',mode='eval').body
    for fn in tree.body:
        if not isinstance(fn,ast.FunctionDef):continue
        if fn.name=='ny_connector_request':
            for node in ast.walk(fn):
                if hasattr(node,'body') and isinstance(node.body,list):
                    node.body[:]=[s for s in node.body if ast.dump(s)!=ast.dump(ny)]
        if fn.name=='final_four_connector_request':
            for node in ast.walk(fn):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='normalize_reviewed_names':
                    if len(node.args)==1 and ast.dump(node.args[0])==ast.dump(new):node.args=[old]
    return tree


class PrimarySalesControls(unittest.TestCase):
    def test_all_other_master_logic_matches_prechange_bx(self):
        old=subprocess.check_output(['git','show','afb6e182dd1719ca6c80ff8a4ac6050f9f64c096:registry_snapshot_server.py'],cwd=ROOT).decode('utf-8')
        current=(ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8')
        self.assertEqual(ast.dump(ast.parse(old)),ast.dump(restore_primary_sales_scope(ast.parse(current))))

    def test_sales_worker_still_generates_dash_and_suffix_prefix_variants(self):
        name='The Education & Health-Alliance, Inc.'
        job={'state':'DC','version':cc.APP_VERSION,'payload':{'organization_name':name,
             'ein':'123456789','mode':'sales','alternate_names':['Discovered Elsewhere']}}
        def lookup(entered,ein,state):
            variants=cc.organization_name_variants(entered,ein)
            for expected in [name,'The Education & Health Alliance, Inc.',
                    'The Education & HealthAlliance, Inc.','The Education and Health-Alliance, Inc.',
                    'Education & Health-Alliance, Inc.','The Education & Health-Alliance']:
                self.assertIn(expected,variants)
            self.assertNotIn('Discovered Elsewhere',variants)
            return {'state':state,'status':'Current','success':True}
        with patch.object(lab_identity,'trial_identity',return_value=TRIAL), \
             patch.object(cc,'run_single_state_lookup_reliably',side_effect=lookup):
            self.assertEqual(queue_engine.execute(cc,job)['status'],'Current')

    def test_worker_ignores_stale_alias_evidence_but_preserves_registry_uncertainty(self):
        for mode in ['sales', 'standard']:
            for status in ['Current', 'Not Registered', 'Unable to Confirm', 'Site Not Reachable', 'Needs Review']:
                job={'state':'DC','version':cc.APP_VERSION,'payload':{
                    'organization_name':'Entered Name','ein':'123456789','mode':mode,
                    'alternate_names':['Supplemental Name']}}
                if mode=='sales':job['sales_identity']={'errors':{'IRS':'HTTPError'}}
                def lookup(name, ein, state):
                    self.assertEqual(cc.known_names_for_ein('123456789'), [] if mode=='sales' else ['Supplemental Name'])
                    self.assertEqual(name,'Entered Name')
                    return {'state':state,'status':status,'success':status in ['Current','Not Registered']}
                with patch.object(lab_identity,'trial_identity',return_value=TRIAL), \
                     patch.object(cc,'run_single_state_lookup_reliably',side_effect=lookup), \
                     patch.object(cc,'sales_identity_evidence',side_effect=AssertionError('No supplemental lookup')), \
                     patch.object(cc,'sales_result_with_identity',side_effect=AssertionError('No supplemental gate')):
                    self.assertEqual(queue_engine.execute(cc,job)['status'],status)

    def test_trial_submission_creates_only_requested_state_jobs(self):
        payload={'organization_name':'Entered Name','ein':'123456789','mode':'sales',
                 'states':['CO','DC'],'alternate_names':['Supplemental Name']}
        with patch.object(dq,'trial_identity',return_value=TRIAL):
            normalized=dq.normalize_submission(payload,['CO','DC'])
            self.assertEqual(normalized['alternate_names'],[])
            cursor=Mock()
            cursor.execute.return_value.fetchone.side_effect=[{'source_version':'fixture','backlog_limit':10},None,None,{'n':0}]
            @contextmanager
            def transaction():yield cursor,1000
            q=dq.Queue.__new__(dq.Queue)
            q.transaction=transaction;q._settle=Mock();q.event=Mock();q.ny_enabled=False
            q.submit('fixture','fixture',normalized,'fixture')
            inserts=[c.args[1] for c in cursor.execute.call_args_list if c.args[0].startswith('INSERT INTO cc_lab_jobs')]
            self.assertEqual([p[2] for p in inserts],['CO','DC'])
            workflow=next(c.args[1] for c in cursor.execute.call_args_list if c.args[0].startswith('INSERT INTO cc_lab_workflows'))
            self.assertEqual(workflow[-1]-workflow[-2],60)

    def test_preparation_keeps_standard_aliases_and_sales_primary_only(self):
        master=types.SimpleNamespace(SUPPORTED_STATES=['CO','NV'],APP_VERSION='fixture-performance-lab',
            NY_CONNECTOR_SIGNING_KEY='fixture-secret-'*4,canonical_ein_digits=cc.canonical_ein_digits)
        for mode in ['sales','standard']:
            seen=[]
            def transport(path,payload,key):
                seen.append(payload);return {'id':'11111111-1111-1111-1111-111111111111'}
            payload={'organization_name':'Entered Name','ein':'123456789','states':['CO','NV'],
                     'mode':mode,'alternate_names':['Supplemental Name'],'request_id':'11111111-1111-1111-1111-111111111111'}
            with patch.object(lab_identity,'trial_identity',return_value=TRIAL):
                staging_workflows.prepare(master,payload,['fixture','device'],transport=transport,external_states={'NV'},external_slots=1)
            self.assertEqual(seen[0]['alternate_names'],[] if mode=='sales' else ['Supplemental Name'])

    def test_actual_browser_workflow_never_waits_for_or_injects_supplemental_names(self):
        with patch.object(lab,'trial_identity',return_value=TRIAL):
            source=lab.final_four_asset('optimized-workflows.js',(ROOT/'web-staging/optimized-workflows.js').read_text(encoding='utf-8'))
        program=r'''const vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
(async()=>{for(const mode of ['sales','standard']){
 const calls=[],lookups=[],window={};
 const fetch=async(u,o)=>{const p=JSON.parse(o.body);calls.push(p);return {ok:true,json:async()=>
   p.action==='start'?{token:'signed'}:{finished:1,results:[{state:'CO',status:'Current',success:true}],
   connector_identity:{ready:true,confirmed:false,names:['Must Never Inject']}}};};
 vm.runInNewContext(SOURCE,{window,fetch,crypto,AbortSignal,performance,location:{origin:'https://staging.compliance-express.com'},setTimeout:f=>setImmediate(f)});
 const rows=await window.CCOptimized.run({apiBase:'https://fixture.test',name:'Entered Name',ein:'123456789',
   mode,states:['CO','NV','GA'],aliases:['Reviewed Alias'],credentials:{},externalLookup:async(state,names)=>{
     lookups.push([...names]);return {state,status:state==='GA'?'Unable to Confirm':'Not Registered',success:state!=='GA'};}});
 assert.deepEqual(calls.find(p=>p.action==='start').alternate_names,mode==='sales'?[]:['Reviewed Alias']);
 assert(lookups.every(a=>JSON.stringify(a)===JSON.stringify(mode==='sales'?[]:['Reviewed Alias'])));
 assert.equal(rows.find(r=>r.state==='NV').status,'Not Registered');
 assert.equal(rows.find(r=>r.state==='GA').status,'Unable to Confirm');
 if(mode==='sales'){
  calls.length=0;
  await window.CCOptimized.run({apiBase:'https://fixture.test',name:'Entered Name',ein:'123456789',mode,
    states:['NV'],credentials:{},externalLookup:async()=>({state:'NV',status:'Not Registered',success:true})});
  assert.equal(calls.length,0,'Connector-only Sales must not create a helper workflow');
 }
}})().catch(e=>{console.error(e);process.exitCode=1;});'''.replace('SOURCE',json.dumps(source))
        r=subprocess.run([str(NODE),'-e',program],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)


if __name__=='__main__':unittest.main(verbosity=2)
