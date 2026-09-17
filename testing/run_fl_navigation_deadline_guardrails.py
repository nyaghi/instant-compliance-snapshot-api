"""Florida recovery must not execute unbounded JavaScript in a stalled page."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class FloridaNavigationTests(unittest.TestCase):
 def run_case(self,failures=1,no_record=False,wrong_name=False):
  now=[0.0];page=MagicMock();visits=[];evaluations=[]
  def goto(url,**kw):
   visits.append((url,kw));now[0]+=.1
   if url!='about:blank' and sum(u!='about:blank' for u,_ in visits)<=failures:
    now[0]+=kw['timeout']/1000;raise TimeoutError('Registry navigation timed out')
  def evaluate(script,*args):
   evaluations.append(script)
   if 'window.stop' in script:
    # A real stalled document can wait indefinitely here. No test may enter it.
    now[0]+=600;raise TimeoutError('Unbounded recovery call')
   return [{'index':0,'text':('Unrelated Local Chapter' if wrong_name else 'Example Relief Inc')+' License/Registration Number CH12345 Expiration Date 12/31/2027 Status Current'}]
  page.goto.side_effect=goto;page.evaluate.side_effect=evaluate
  page.expect_navigation.return_value.__enter__.return_value.value=SimpleNamespace(status=200)
  def sleep(seconds):now[0]+=seconds
  with patch.object(c.time,'monotonic',side_effect=lambda:now[0]),patch.object(c.time,'sleep',side_effect=sleep),patch.object(c,'reviewed_queries_first',return_value=['Example Relief Inc']),patch.object(c.checker,'find_visible_input',return_value=page),patch.object(c,'readable_page_text',return_value='No records found' if no_record else 'Example Relief Inc CH12345'),patch.object(c,'no_registry_results_seen',return_value=no_record),patch.object(c,'registry_candidate_fields',return_value={'status':'Current'}):
   result=c.search_fl(page,SimpleNamespace(organization_name='Example Relief Inc',ein='123456789'))
  return result,visits,evaluations,now[0]
 def test_timed_out_navigation_recovers_current_without_javascript(self):
  result,visits,evaluations,seconds=self.run_case()
  self.assertEqual(result.status,'Current');self.assertEqual(result.matched_registry_identifier,'CH12345')
  self.assertFalse(any('window.stop' in s for s in evaluations));self.assertLess(seconds,44)
  self.assertTrue(any(url=='about:blank' and kw['timeout']<=3000 for url,kw in visits))
 def test_repeated_navigation_failure_remains_bounded_and_inconclusive(self):
  result,visits,evaluations,seconds=self.run_case(failures=10)
  self.assertFalse(result.success);self.assertNotEqual(result.status,c.checker.STATUS_NOT_REGISTERED)
  self.assertFalse(any('window.stop' in s for s in evaluations));self.assertLess(seconds,50)
  self.assertTrue(all(0<kw['timeout']<=12000 for _,kw in visits))
 def test_completed_negative_unchanged(self):
  result,*_=self.run_case(failures=0,no_record=True)
  self.assertEqual(result.status,c.checker.STATUS_NOT_REGISTERED);self.assertTrue(result.success)
 def test_completed_unrelated_record_not_accepted(self):
  result,*_=self.run_case(failures=0,wrong_name=True)
  self.assertEqual(result.status,c.checker.STATUS_NOT_REGISTERED);self.assertFalse(result.matched_registry_identifier)

if __name__=='__main__':unittest.main()
