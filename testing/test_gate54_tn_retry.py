"""Execute the served workflow under a deterministic clock, without a browser."""
import ast,json,os,subprocess,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from deployment import performance_lab as lab

class TennesseeRecoveryDeadline(unittest.TestCase):
    def test_70_recorded_organizations_original_deadline_and_regression_controls(self):
        trial={'origin':'https://fixture-final-four.onrender.com'}
        old=subprocess.check_output(['git','show','8a5ad0b:deployment/performance_lab.py'],cwd=ROOT).decode('utf-8')
        baseline=types.ModuleType('tn_sd_baseline');baseline.__dict__.update(lab.__dict__)
        exec(compile(ast.Module(body=[n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='final_four_asset'],type_ignores=[]),'baseline-lab','exec'),baseline.__dict__)
        with patch.object(lab,'trial_identity',return_value=trial),patch.object(lab,'LAB_ORIGIN',trial['origin']),patch.dict(baseline.__dict__,{'trial_identity':lambda:trial,'LAB_ORIGIN':trial['origin']}):
            current=lab.lab_asset('/optimized-workflows.js')[0].decode('utf-8')
            with patch.object(lab,'final_four_asset',baseline.final_four_asset):
                previous=lab.lab_asset('/optimized-workflows.js')[0].decode('utf-8')
        cases=json.loads((ROOT/'testing/fixtures/gate54-state-controls.json').read_text())['cases']
        program=(ROOT/'testing/test_gate54_tn_retry.cjs').read_text(encoding='utf-8')
        node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        result=subprocess.run([str(node),'-e',program],input=json.dumps({'current':current,'previous':previous,'cases':cases}),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
        output=json.loads(result.stdout)
        self.assertTrue(output['passed']);self.assertEqual(output['recorded_organizations'],70)
        out=Path(os.environ.get('CC_GATE54_TEST_OUTPUT',str(ROOT)));out.mkdir(exist_ok=True,parents=True)
        (out/'TN-70-RESULTS.json').write_text(json.dumps(output,indent=2))

if __name__=='__main__':unittest.main()
