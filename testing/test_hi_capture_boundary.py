import unittest
from unittest.mock import patch
from deployment import state_snapshots as m
from testing.test_md_capture_finish import Clock

class Page:
 def __init__(self,clock,delay=.2,changed=False):
  self.clock=clock;self.delay=delay;self.changed=changed;self.shots=0;self.url='https://charity.ehawaii.gov/charity/123456789/details.html'
 def inner_text(self,selector,timeout):
  self.clock.spend(.05,timeout)
  return 'Book Trust 123456789 Active'+(' changed' if self.changed and self.shots else '')
 def locator(self,selector):return self
 def evaluate(self,expression,timeout):
  self.clock.spend(.05,timeout);return dict(width=1200,height=1000)
 def screenshot(self,**kw):
  self.clock.spend(self.delay,kw['timeout']);self.shots+=1;return b'original-source-image'

class HawaiiCaptureBoundary(unittest.TestCase):
 def run_case(self,remaining=2.302347,deadline=400,**opts):
  clock=Clock();clock.time=clock.monotonic;page=Page(clock,**opts);run=m.CaptureRun('Book Trust','123456789','HI');run.page_capture_stop=clock.now+remaining
  token=m.DEADLINE.set(deadline)
  try:
   with patch.object(m,'time',clock),patch.object(m,'workflow_call',side_effect=lambda stage,fn,scope,*a,**kw:fn(*a,**kw)):
    run.page(page)
  finally:m.DEADLINE.reset(token)
  return run,page,clock
 def test_observed_boundary_captures_original_within_original_stop(self):
  r,p,c=self.run_case();self.assertEqual(len(r.documents),1);self.assertEqual(r.documents[0][1],b'original-source-image');self.assertLess(c.now,r.page_capture_stop-1)
 def test_healthy_capture_unchanged(self):
  r,p,c=self.run_case(remaining=6);self.assertEqual(len(r.documents),1);self.assertEqual(p.shots,1)
 def test_changed_source_is_rejected(self):
  r,p,c=self.run_case(changed=True);self.assertEqual(r.documents,[]);self.assertIn('source_page_changed_during_capture',r.errors)
 def test_slow_capture_stops_without_extra_allowance(self):
  r,p,c=self.run_case(delay=3);self.assertEqual(r.documents,[]);self.assertLess(c.now,r.page_capture_stop)
 def test_expired_local_and_task_deadlines_are_not_extended(self):
  for remaining,deadline in [(0,400),(.5,400),(3,102)]:
   with self.subTest(remaining=remaining,deadline=deadline):
    r,p,c=self.run_case(remaining,deadline);self.assertEqual(r.documents,[]);self.assertEqual(p.shots,0)

if __name__=='__main__':unittest.main()
