"""MS-only detail recovery controls; synthetic page timings, no network."""
import sys,unittest,re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class Tests(unittest.TestCase):
 def probe(self,ready_at=0,text='Filing Status: Current - Registered\nExpiration Date: 11/15/2026',click_failures=0,read_failure=False):
  clock=[0.0];page=Mock();link=Mock();result=SimpleNamespace(source_attempts=[])
  def click(**kw):
   if link.click.call_count<=click_failures:
    clock[0]+=kw['timeout']/1000
    raise TimeoutError('test')
  link.click.side_effect=click
  def read(**kw):
   if read_failure:
    clock[0]+=kw['timeout']/1000
    raise TimeoutError('test')
   return text if clock[0]>=ready_at else 'Search results still loading'
  page.locator.return_value.inner_text.side_effect=read
  page.wait_for_timeout.side_effect=lambda ms:clock.__setitem__(0,clock[0]+ms/1000)
  def extract(body,labels):
   for label in labels:
    match=re.search(re.escape(label)+r':\s*([^\n]+)',body)
    if match:return match.group(1)
   return ''
  module=SimpleNamespace(extract_labeled_value_from_text=extract,parse_mmddyyyy_date=c.parse_due_date)
  with patch.object(c.time,'perf_counter',side_effect=lambda:clock[0]):
   body=c.ms_read_detail_with_recovery(page,link,module,result)
  self.assertLessEqual(clock[0],8)
  self.assertLessEqual(link.click.call_count,2)
  return body,result,clock[0],link
 def test_immediate_detail_has_no_extra_wait(self):
  body,r,t,link=self.probe();self.assertIn('11/15/2026',body);self.assertEqual(t,0);self.assertEqual(r.source_attempts,[]);self.assertEqual(link.click.call_count,1)
 def test_delayed_detail_recovers_without_reclick(self):
  body,r,t,link=self.probe(ready_at=4);self.assertIn('Expiration Date',body);self.assertIn('recovered',' '.join(r.source_attempts));self.assertEqual(link.click.call_count,1)
 def test_navigation_timeout_can_already_have_loaded_detail(self):
  body,r,t,link=self.probe(click_failures=1);self.assertIn('Expiration Date',body);self.assertEqual(link.click.call_count,1)
 def test_failed_click_retried_once_within_total_budget(self):
  body,r,t,link=self.probe(ready_at=7,click_failures=1);self.assertIn('Expiration Date',body);self.assertEqual(link.click.call_count,2)
 def test_persistent_missing_date_is_bounded_and_diagnosed(self):
  body,r,t,link=self.probe(text='Filing Status: Current - Registered');self.assertEqual(t,6);self.assertEqual(len(r.source_attempts),2);self.assertNotIn('Expiration Date',body)
 def test_read_timeouts_preserve_diagnostics(self):
  body,r,t,link=self.probe(read_failure=True);self.assertEqual(body,'');self.assertIn('body read failed',' '.join(r.source_attempts))
 def test_terminal_status_does_not_wait_for_unnecessary_date(self):
  for status in ['Exempt','Closed','Withdrawn','Canceled']:
   with self.subTest(status=status):self.assertEqual(self.probe(text='Filing Status: '+status)[2],0)
 def test_expire_date_variant(self):
  body,r,t,link=self.probe(text='Filing Status: Current\nExpire Date: 11/15/2026');self.assertEqual(t,0)
 def test_unparseable_date_does_not_pretend_to_be_ready(self):
  body,r,t,link=self.probe(text='Filing Status: Current\nExpiration Date: Loading');self.assertEqual(t,6)

if __name__=='__main__':unittest.main()
