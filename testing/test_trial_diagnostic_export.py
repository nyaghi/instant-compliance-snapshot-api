"""The isolated lab export preserves a first-pass trace without changing rows."""
import base64
import io
import json
from pathlib import Path
import re
import subprocess
import unittest
import zipfile
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
        begin = page.index('      window.__CCLabStateTrace = [];')
        end = page.index('      startElapsedTimer();', begin)
        reset = page[begin:end]
        exporter = (ROOT / 'web-staging/excel-export.js').read_text(encoding='utf-8')
        program = r'''const vm=require('node:vm'), assert=require('node:assert/strict');
let downloaded, removed=false, hidden=false, cleared=false;
const context={
  latestResults:[{organization_name:'Example Charity',ein:'012345678',state:'MS',status:'Current',
    evidence_url:'/state-snapshots/'+'a'.repeat(64)+'.pdf'}],
  commentsWithRegistryFooter:()=>'',window:{__CCLabStateTrace:[{state:'OLD'}]},
  document:{createElement:()=>({click(){}}),getElementById:()=>({remove(){removed=true}})},
  resultPanel:{classList:{add(name){hidden=name==='hidden'}}},resultRows:{replaceChildren(){cleared=true}},
  URL, location:{origin:'https://fixture-final-four.onrender.com'}, Blob,TextEncoder,Uint8Array,DataView,
  setTimeout:()=>{}, Date,JSON,
};
const urls={createObjectURL(blob){downloaded=blob;return 'blob:test'},revokeObjectURL(){}};
const sandbox=vm.createContext(context);
vm.runInContext(EXPORTER,sandbox);
vm.runInContext(RESET,sandbox);
assert.ok(removed&&hidden&&cleared);
context.window.__CCLabStateTrace.push({state:'MS',stage:'first pass'},{state:'MS',stage:'row retry'});
context.URL=Object.assign(class extends URL {},urls);
vm.runInContext(FUNCTION+'\ndownloadExcel();',sandbox);
downloaded.arrayBuffer().then(b=>process.stdout.write(Buffer.from(b).toString('base64')));
'''.replace('EXPORTER', json.dumps(exporter)).replace('RESET', json.dumps(reset)).replace('FUNCTION', json.dumps(match.group(0)))
        result = subprocess.run([str(NODE)], input=program, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(result.stdout))) as book:
            diagnostics = json.loads(book.read('cc-diagnostics.json'))
            self.assertEqual([e['stage'] for e in diagnostics['events']], ['first pass', 'row retry'])
            self.assertIn(b'01-2345678', book.read('xl/worksheets/sheet1.xml'))
            self.assertIn(b'Current', book.read('xl/worksheets/sheet1.xml'))
            self.assertIn(b'/state-snapshots/', book.read('xl/worksheets/_rels/sheet2.xml.rels'))


if __name__ == '__main__':
    unittest.main()
