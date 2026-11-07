import ast,copy,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m

NAME='American Institutes for Research in the Behavioral Sciences'
HEADERS=['Name','License/Registration#','Status','Registration Type','Issued Date','Expiration Date','Address','City','State','Zip','Print']
ROWS=json.loads((Path(__file__).parent/'fixtures/gates31-33/AL-RESEARCH-ROWS.json').read_text(encoding='utf-8'))
def payload(rows):return dict(headers=HEADERS,rows=rows,total=len(rows),complete=True,verification_pending=False)

class PendingApplication(unittest.TestCase):
 def test_observed_complete_grid_baseline_rejects_candidate_retains(self):
  source=subprocess.check_output(['git','show','abeb0add0b07544be2d95ededa936610770d6e77:registry_snapshot_server.py'],text=True,encoding='utf-8')
  node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='al_charity_search_evidence')
  scope=dict(m.__dict__);exec(compile(ast.Module(body=[node],type_ignores=[]),'baseline','exec'),scope)
  with self.assertRaisesRegex(ValueError,'identity is missing'):scope['al_charity_search_evidence'](payload(ROWS))
  rows=m.al_charity_search_evidence(payload(ROWS))
  pending=next(r for r in rows if r['name']==ROWS[0][0])
  self.assertTrue(pending['registration_identifier_missing']);self.assertEqual(pending['raw_status'],'Pending')
 def test_real_identity_path_excludes_unrelated_but_holds_matching(self):
  for name,expected in [(NAME,'Not Registered'),(ROWS[0][0],'Needs Review')]:
   def evidence(q):return dict(payload(ROWS),query=q,state='AL')
   with patch.object(m,'licensed_charity_names',return_value=([name],[])):
    result=m.final_four_browser_lookup(m.checker.Organization(name,'250965219'),'AL',evidence)
   self.assertEqual(result.status,expected)
   if expected=='Needs Review':self.assertFalse(result.success)
 def test_issued_missing_identity_and_incomplete_guards_retained(self):
  for change in [(2,'Active'),(4,'11/07/2026'),(5,'11/07/2027'),(0,'')]:
   rows=copy.deepcopy(ROWS);rows[0][change[0]]=change[1]
   with self.subTest(change=change),self.assertRaises(ValueError):m.al_charity_search_evidence(payload(rows))
  p=payload(ROWS);p['total']+=1
  with self.assertRaises(ValueError):m.al_charity_search_evidence(p)

if __name__=='__main__':unittest.main()
