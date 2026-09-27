"""Conservative MS fallback identity, full response, and recorded controls."""
import ast,copy,json,subprocess,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import registry_snapshot_server as c
NAME='Make-A-Wish Foundation of America'
REGIONAL='Make-A-Wish Foundation of the Mid-South'
EIN='860481941'
ALIASES=['Make-A-Wish','Make-A-Wish America','MAKE- A- WISH FOUNDATION OF AMERICA','MAWF','MAKE-A-WISH FOUNDATION']

def record(name=NAME,status='Upcoming Filing',**kwargs):
 return SimpleNamespace(organization_name=name,matched_registry_name=name,status=status,success=True,
  raw_status_text='Closed/Withdrawn | Expiration Date: 01/15/2026' if status.startswith('Closed') else status,
  source_note='',source_url='https://charities.sos.ms.gov/',**kwargs)

class Tests(unittest.TestCase):
 def setUp(self):self.token=c.REVIEWED_NAME_CONTEXT.set({EIN:tuple(ALIASES)})
 def tearDown(self):c.REVIEWED_NAME_CONTEXT.reset(self.token)
 def run_results(self,results,name=NAME,ein=EIN):
  org=c.checker.Organization(name,ein)
  with patch.object(c,'ms_name_search_plan',return_value=[NAME,*ALIASES][:len(results)]),patch.object(c,'search_ms_fast',side_effect=results) as search:
   result=c.search_batch_browser_state(Mock(),org,'MS')
  return result,search
 def test_reported_regional_record_never_assigns_closed_to_national(self):
  r,_=self.run_results([record(REGIONAL,'Closed / Withdrawn / Canceled')])
  self.assertEqual(c.public_status(r),'Needs Review');self.assertFalse(r.success)
  self.assertEqual(r.reason_code,'MS_IDENTITY_UNCONFIRMED')
  self.assertFalse(r.matched_registry_name);self.assertFalse(r.matched_registry_identifier)
 def test_continues_existing_variants_and_finds_national(self):
  r,search=self.run_results([record(REGIONAL,'Closed / Withdrawn / Canceled'),record()])
  self.assertEqual(search.call_count,2);self.assertEqual(r.matched_registry_name,NAME)
  self.assertEqual(c.public_status(r),'Upcoming Filing')
 def test_later_completed_negatives_do_not_erase_identity_review(self):
  r,_=self.run_results([record(REGIONAL,'Closed / Withdrawn / Canceled'),record('', 'Not Registered')])
  self.assertEqual(c.public_status(r),'Needs Review')
 def test_same_ein_verified_on_candidate_can_confirm_identity(self):
  r,_=self.run_results([record(REGIONAL,'Current',verified_registry_ein=EIN)])
  self.assertEqual(c.public_status(r),'Current')
 def test_different_verified_ein_rejects_even_exact_name(self):
  r,_=self.run_results([record(NAME,'Current',verified_registry_ein='123456789')])
  self.assertEqual(c.public_status(r),'Needs Review')
 def test_complete_reviewed_former_legal_name_still_accepted(self):
  r,_=self.run_results([record('MAKE- A- WISH FOUNDATION OF AMERICA','Current')])
  self.assertEqual(c.public_status(r),'Current')
 def test_exact_local_organization_request_still_accepted(self):
  r,_=self.run_results([record(REGIONAL,'Current')],name=REGIONAL,ein='123456789')
  self.assertEqual(c.public_status(r),'Current')
 def test_sales_full_reviewed_alias_accepts_and_ampersand_equivalence(self):
  ein='521089824';name='National Low Income Housing Coalition'
  c.REVIEWED_NAME_CONTEXT.set({ein:('National Low Income Housing Coalition And Low Income Housing',)})
  r,_=self.run_results([record('National Low Income Housing Coalition & Low Income Housing','Upcoming Filing')],name=name,ein=ein)
  self.assertEqual(c.public_status(r),'Upcoming Filing')
 def test_terminal_status_for_confirmed_org_unchanged(self):
  for status in ['Closed / Withdrawn / Canceled','Exempt','Delinquent','Current']:
   with self.subTest(status=status):
    r,_=self.run_results([record(NAME,status)]);self.assertEqual(c.public_status(r),status)
 def test_confirmed_empty_search_stays_negative(self):
  c.REVIEWED_NAME_CONTEXT.set({})
  r,_=self.run_results([record('','Not Registered')]);self.assertEqual(c.public_status(r),'Not Registered')
 def test_unreachable_is_not_negative(self):
  r,_=self.run_results([record('','Site Not Reachable')]);self.assertEqual(c.public_status(r),'Site Not Reachable')
 def test_comment_and_response_do_not_claim_a_match_or_copy_dates(self):
  r,_=self.run_results([record(REGIONAL,'Closed / Withdrawn / Canceled')])
  org=c.checker.Organization(NAME,EIN)
  with patch.object(c,'enrich_registration_date_sources'):
   data=c.response_data_for_lookup(r,'',org,NAME,EIN,'MS',time.perf_counter())
  self.assertEqual(data['status'],'Needs Review');self.assertFalse(data['success'])
  self.assertIn(REGIONAL,data['comments']);self.assertIn('separate regional organization',data['comments'])
  self.assertNotIn('Registry match:',data['comments']);self.assertFalse(data['registration_date'])
  self.assertFalse(data['renewal_filing_value'])
 def test_recorded_twenty_org_control_results_unchanged(self):
  rows=json.loads((ROOT/'testing/fixtures/ms-national-identity-controls.json').read_text())['rows']
  self.assertEqual(len(rows),40)
  for row in rows:
   with self.subTest(ein=row['ein']):
    ein=c.canonical_ein_digits(row['ein']);c.REVIEWED_NAME_CONTEXT.set({ein:tuple(row['alternate_names'])})
    org=c.checker.Organization(row['organization_name'],row['ein']);source=row['result']
    with patch.object(c,'ms_name_search_plan',return_value=[org.organization_name]),patch.object(c,'equivalent_name_queries',return_value=[org.organization_name]),patch.object(c,'search_ms_fast',return_value=SimpleNamespace(organization_name=org.organization_name,**source)):
     r=c.search_batch_browser_state(Mock(),org,'MS')
    self.assertEqual(c.public_status(r),source['status'])
    self.assertEqual(r.matched_registry_name,source['matched_registry_name'])
 def test_runtime_scope_and_budgets(self):
  old=ast.parse(subprocess.check_output(['git','show','19c6083:registry_snapshot_server.py'],cwd=ROOT).decode('utf-8'))
  new=ast.parse((ROOT/'registry_snapshot_server.py').read_text(encoding='utf-8'))
  from testing.capacity_lab.test_fl_source_independence import restore_source_gate
  restore_source_gate(new,old)
  oldmap={n.name:n for n in old.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  newmap={n.name:n for n in new.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  changed={k for k in oldmap if ast.dump(oldmap[k])!=ast.dump(newmap[k])}
  self.assertEqual(changed,{'search_batch_browser_state','comments_for_result_base','search_ar_serialized','run_single_state_lookup_reliably'})
  self.assertEqual(set(newmap)-set(oldmap),{'lab_sales_ar_access_block_is_terminal'})
  self.assertEqual(set(oldmap)-set(newmap),set())
  def budgets(node):
   return [ast.dump(n) for n in ast.walk(node) if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='ms_deadline' for x in n.targets)]
  self.assertEqual(budgets(oldmap['search_batch_browser_state']),budgets(newmap['search_batch_browser_state']))

if __name__=='__main__':unittest.main(verbosity=2)
