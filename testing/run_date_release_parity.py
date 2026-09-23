"""Guard the stable lookup workflow while adding display-only registration dates."""
import ast, hashlib, json, statistics, subprocess, sys, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import registry_snapshot_server as cc

BASE = '06e5e53'
def previous(name):
    return subprocess.check_output(['git', 'show', BASE + ':' + name], cwd=ROOT).decode('utf-8').replace('\r\n','\n')

class StableDateRelease(unittest.TestCase):
    def test_master_only_adds_metadata_and_version(self):
        tree = ast.parse((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        old = ast.parse(previous('registry_snapshot_server.py'))
        helpers={'registration_date_metadata','registration_source_date','registration_date_result_confirmed','registration_date_budget_available','fl_registration_issue_evidence','enrich_registration_date_sources','co_registration_renewal_evidence','renewal_filing_metadata'}
        tree.body = [n for n in tree.body if not isinstance(n, ast.FunctionDef) or n.name not in helpers]
        class RemoveDateOnlyChanges(ast.NodeTransformer):
            def visit_Assign(self,node):
                if any(isinstance(t,ast.Attribute) and t.attr in {'_cc_registration_records','_cc_registration_date_detail','_cc_registration_date_evidence'} for t in node.targets):
                    return None
                return self.generic_visit(node)
            def visit_Dict(self,node):
                pairs=[(k,v) for k,v in zip(node.keys,node.values) if not isinstance(k,ast.Constant) or k.value != 'date_records']
                node.keys=[k for k,v in pairs];node.values=[v for k,v in pairs]
                return self.generic_visit(node)
            def visit_Expr(self,node):
                if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='enrich_registration_date_sources':return None
                return self.generic_visit(node)
            def visit_If(self,node):
                if ast.unparse(node.test)=="page and state == 'CO'" and len(node.body)==1 and 'co_registration_renewal_evidence' in ast.unparse(node.body[0]):return None
                return self.generic_visit(node)
        tree=RemoveDateOnlyChanges().visit(tree)
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_VERSION' for t in node.targets):
                node.value = next(n.value for n in old.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='APP_VERSION' for t in n.targets))
            if isinstance(node, ast.FunctionDef) and node.name=='response_data_for_lookup':
                node.body = [n for n in node.body if not (isinstance(n,ast.Expr) and ast.unparse(n) in {"data.update(registration_date_metadata(result, data['status'], body))", "data.update(renewal_filing_metadata(result, data, data['status'], body))"})]
        self.assertEqual(ast.dump(tree), ast.dump(old))

    def test_state_logic_discovery_and_connector_unchanged(self):
        for name in ['Charity_Checker_Script for 13_states.py','web-staging/organization-identity.js','web-staging/ny-connector.js']:
            current=(ROOT/name).read_text(encoding='utf-8')
            if name=='Charity_Checker_Script for 13_states.py':
                current=current.replace('entity, match_basis, registrations))','entity, match_basis))')
                current=current.replace('entity, match_basis, registrations = max','entity, match_basis = max')
                current=current.replace('        # Retain already-fetched selected-entity data for master metadata extraction.\n        result._cc_registration_records = registrations\n','')
            self.assertEqual(hashlib.sha256(current.encode()).hexdigest(), hashlib.sha256(previous(name).encode()).hexdigest(), name)

    def test_frontend_state_workflow_unchanged(self):
        old = previous('web-staging/index.html')
        new = (ROOT/'web-staging/index.html').read_text(encoding='utf-8')
        start = '    async function runStateChecks('
        self.assertTrue(start in old)
        def body(text):
            section=text[text.index(start):]
            return section[:section.index('\n    stateCheckboxes.forEach',len(start))]
        self.assertEqual(body(new),body(old))
        self.assertNotIn('CCSales',new)

    def test_metadata_has_no_io_and_does_not_mutate_status(self):
        durations=[]
        for _ in range(100):
            for state in cc.SUPPORTED_STATES:
                r=cc.checker.StateResult('Control Foundation','12-3456789',state,'Current','https://example.org/registry')
                r.success=True;r.matched_registry_name='Control Foundation'
                r.raw_status_text='Registration Date: 2010-02-03'
                before=dict(vars(r));started=time.perf_counter()
                cc.renewal_filing_metadata(r,cc.registration_date_metadata(r,'Current'),'Current')
                durations.append(time.perf_counter()-started)
                self.assertEqual(vars(r),before)
        print('METADATA_TIMING '+json.dumps({'calls':len(durations),'median_ms':statistics.median(durations)*1000,'p99_ms':sorted(durations)[int(.99*len(durations))]*1000,'max_ms':max(durations)*1000}))

if __name__=='__main__': unittest.main()
