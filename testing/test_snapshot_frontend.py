"""Compile the actually assembled frontend; no user browser or network."""
import json,re,subprocess,sys,unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deployment import performance_lab as lab
class Scripts(HTMLParser):
    def __init__(self):super().__init__();self.current=None;self.inline=[];self.states=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script' and not a.get('src') and a.get('type','') not in {'application/json','application/ld+json'}:self.current=[]
        if tag=='input' and a.get('name')=='states':self.states.append(a.get('value'))
    def handle_data(self,text):
        if self.current is not None:self.current.append(text)
    def handle_endtag(self,tag):
        if tag=='script' and self.current is not None:self.inline.append(''.join(self.current));self.current=None
class Frontend(unittest.TestCase):
    def test_actual_trial_assembly_keeps_38_states_and_saved_pdf_transport(self):
        with patch.object(lab,'trial_identity',return_value={'origin':lab.LAB_ORIGIN}):
            files={name:lab.lab_asset('/'+name)[0].decode() for name in ['index.html','identity-review.js','ny-connector.js']}
        parser=Scripts();parser.feed(files['index.html'])
        self.assertEqual(len(parser.states),38);self.assertEqual(len(set(parser.states)),38)
        self.assertEqual(files['index.html'].count('CCIdentityReview?.renderEvidence'),1)
        self.assertIn('state_snapshot: completed.state_snapshot',files['ny-connector.js'])
        self.assertIn('View State Snapshot (PDF)',files['identity-review.js'])
        self.assertNotIn('View state record',files['identity-review.js'])
        scripts=parser.inline+[files['identity-review.js'],files['ny-connector.js']]
        result=subprocess.run(['node','-e',"const vm=require('node:vm');const fs=require('node:fs');for(const text of JSON.parse(fs.readFileSync(0,'utf8')))new vm.Script(text);"],input=json.dumps(scripts),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main(verbosity=2)
