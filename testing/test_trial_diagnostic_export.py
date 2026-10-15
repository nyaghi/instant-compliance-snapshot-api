"""The isolated lab export preserves a first-pass trace without changing rows."""
import json
from pathlib import Path
import re
import subprocess
import unittest
from unittest.mock import patch

from deployment import performance_lab


ROOT = Path(__file__).resolve().parents[1]
NODE = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'


class TrialDiagnosticExport(unittest.TestCase):
    def test_tennessee_completed_message_reaches_dom_trace_without_other_state_regression(self):
        with patch.object(performance_lab, 'trial_identity', return_value={'origin': 'https://fixture-final-four.onrender.com'}):
            page = performance_lab.final_four_asset('index.html', (ROOT / 'web-staging/index.html').read_text(encoding='utf-8'))
            connector = performance_lab.final_four_asset('ny-connector.js', (ROOT / 'web-staging/ny-connector.js').read_text(encoding='utf-8'))
        start = page.index('              if (detail && [')
        end_marker = '                traceNode.textContent = JSON.stringify(events);\n              }'
        capture = page[start:page.index(end_marker, start)+len(end_marker)]
        expression = re.search(r'(\[[^\]]+\]\.includes\(registryState\) && Array\.isArray\(completed\.trial_diagnostics\) \? \{trial_diagnostics:completed\.trial_diagnostics\} : \{\})', connector)
        self.assertIsNotNone(expression)
        program = r'''const vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),context={window:{},Date,JSON,document:{getElementById:id=>nodes.get(id),
 createElement:()=>({}),body:{appendChild:n=>nodes.set(n.id,n)}}};
vm.createContext(context);vm.runInContext('function capture(detail){'+CAPTURE+'}',context);
for(const registryState of ['TN','MS','NC','GA']){
 const completed={trial_diagnostics:[{type:'tn-dom',detail:'{"phase":"public-error","category":"grid-binding"}'}]};
 const extra=new Function('registryState','completed','return ('+EXPRESSION+')')(registryState,completed);
 context.capture({state:registryState,stage:'browser query returned',...extra});
}
const trace=JSON.parse(nodes.get('cc-lab-state-trace').textContent);
assert.deepEqual(trace.map(e=>e.state),['TN','MS','NC','GA']);
assert.equal(trace[0].trial_diagnostics[0].type,'tn-dom');
assert.equal(JSON.parse(trace[0].trial_diagnostics[0].detail).category,'grid-binding');
console.log('TN message-to-DOM trace and mature-state controls passed');'''.replace('CAPTURE',json.dumps(capture)).replace('EXPRESSION',json.dumps(expression[1]))
        result = subprocess.run([str(NODE), '-e', program], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_excel_download_contains_trace_and_unchanged_results_table(self):
        with patch.object(performance_lab, 'trial_identity', return_value={'origin': 'https://fixture-final-four.onrender.com'}):
            page = performance_lab.final_four_asset('index.html', (ROOT / 'web-staging/index.html').read_text(encoding='utf-8'))
        function = page[page.index('    function downloadExcel() {'):page.index('    downloadExcelButton.addEventListener(')]
        function = function[:function.index('\n    function ', 20)] if '\n    function ' in function[20:] else function
        # Parse just the declared function body, avoiding unrelated page code.
        match = re.search(r'    function downloadExcel\(\) \{[\s\S]*?\n    \}', function)
        self.assertIsNotNone(match)
        program = r'''const vm=require('node:vm'), assert=require('node:assert/strict');
let downloaded;
const link={click(){}};
const context={
  latestResults:[{organization_name:'Example Charity',ein:'012345678',state:'MS',status:'Unable to Confirm',comments:'Search incomplete'}],
  formatEin:()=> '01-2345678', commentsWithRegistryFooter:r=>r.comments,
  window:{__CCLabStateTrace:[{at:1000,state:'MS',stage:'browser query started',query:'Example Charity'},
    {at:4500,state:'MS',stage:'browser query returned',reason:'NY_CONNECTOR_INCOMPLETE'}]},
  document:{createElement:()=>link}, URL:{createObjectURL:blob=>(downloaded=blob,'blob:test'),revokeObjectURL(){}},
  Blob,Date,encodeURIComponent,JSON,String
};
vm.createContext(context);vm.runInContext(FUNCTION+'\ndownloadExcel();',context);
(async()=>{
  const output=await downloaded.text();
  const match=output.match(/^<!--CC_LAB_TRACE_V1:([\s\S]*?)-->/);
  assert.ok(match,'trace is embedded in the existing download');
  const trace=JSON.parse(decodeURIComponent(match[1]));
  assert.equal(trace.schema,'cc-lab-trace-v1');
  assert.equal(trace.events.length,2);
  assert.equal(trace.events[1].reason,'NY_CONNECTOR_INCOMPLETE');
  assert.equal((output.match(/<table>/g)||[]).length,1);
  assert.ok(output.includes('<td>MS</td><td>Unable to Confirm</td>'));
  assert.ok(output.includes('<td>01-2345678</td>'));
  process.stdout.write('trace export and results table passed');
})().catch(e=>{console.error(e);process.exitCode=1});'''.replace('FUNCTION', json.dumps(match.group(0)))
        result = subprocess.run([str(NODE), '-e', program], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
