"""Actual MD capture path, deterministic source timing and record changes."""
import copy, unittest
from types import SimpleNamespace
from unittest.mock import patch
from deployment import source_visual_adapters as m

class Clock:
 def __init__(self): self.now=100.0
 def monotonic(self): return self.now
 perf_counter=monotonic
 def spend(self,seconds,timeout=None):
  if timeout is not None and seconds>timeout/1000:
   self.now+=timeout/1000;raise TimeoutError('modeled timeout')
  self.now+=seconds

class Node:
 def __init__(self,p,kind,label=None): self.p=p;self.kind=kind;self.label=label
 def locator(self,selector): return Node(self.p,'field' if selector=='.dvce-model-property' else self.kind,self.label)
 def filter(self,has=None,has_text=None):
  return Node(self.p,self.kind,has.label if has else self.label)
 def count(self): return int(self.p.alert) if self.kind=='alert' else 1
 def is_visible(self): return self.p.alert
 def wait_for(self,state,timeout):
  if self.kind=='panel': self.p.clock.spend(self.p.panel_delay,timeout)
  elif self.kind=='alert':
   self.p.clock.spend(self.p.dismiss_delay,timeout);self.p.alert=False
   if self.p.change_alert:self.p.fields['Registration Status']='Expired'
 def inner_text(self,timeout=None): return self.p.fields[self.label]
 def all_inner_texts(self): return [k+': '+v for k,v in self.p.fields.items()]
 def click(self,timeout): self.p.clicks+=1

class Page:
 def __init__(self,clock,**opts):
  self.clock=clock;self.url='';self.alert=opts.get('alert',True);self.closed=False;self.shots=0;self.clicks=0
  self.nav=opts.get('nav',26.54);self.panel_delay=opts.get('panel_delay',2.0)
  self.dismiss_delay=opts.get('dismiss_delay',.5);self.change_alert=opts.get('change_alert',False)
  self.change_shot=opts.get('change_shot',False);self.shot_delay=opts.get('shot_delay',.2)
  self.foreign_url=opts.get('foreign_url',False);self.verification=opts.get('verification',False)
  self.fields={'Charity Name':"Crohn's & Colitis Foundation, Inc.",'Charity ID':'271','Registration Status':'Pending','Latest Approval Date':'11/01/2026'}
  self.fields.update(opts.get('fields',{}))
 def set_extra_http_headers(self,v): pass
 def goto(self,url,referer,wait_until,timeout):
  self.clock.spend(self.nav,timeout);self.url=url+('/foreign' if self.foreign_url else '')
  return SimpleNamespace(status=200)
 def get_by_role(self,role,name,exact=True):
  return Node(self,{'tabpanel':'panel','button':'alert','heading':'heading'}[role],name)
 def inner_text(self,selector,timeout): return '\n'.join(self.fields.values())+(' Verify you are human' if self.verification else '')
 def screenshot(self,**kwargs):
  self.clock.spend(self.shot_delay,kwargs['timeout']);self.shots+=1
  if self.change_shot:self.fields['Charity ID']='999'
  return b'original-modeled-pixels'
 def close(self): self.closed=True

class MarylandFinishTests(unittest.TestCase):
 def run_case(self,deadline=400,foreign_ein=False,**opts):
  clock=Clock();p=Page(clock,**opts);docs=[]
  result=dict(state='MD',ein='136193105',success=True,status='Pending',matched_registry_name="Crohn's & Colitis Foundation, Inc.",matched_registry_identifier='271',source_url='https://onestop.md.gov/list_views/62f3e1797f7e3200016a3dab')
  original=copy.deepcopy(result)
  hint=dict(name=result['matched_registry_name'],url='https://onestop.md.gov/detail_views/62f3e17b7f7e3200016a4b6c/entry/'+'a'*24,source_fields=dict(status='Pending',year='2024'))
  run=SimpleNamespace(state='MD',ein='999999999' if foreign_ein else '136193105',source_detail_hints={'271':hint},visual_adapter_facts=[],capture_ms=0,documents=docs,document=lambda *a,**kw:docs.append((a,kw)))
  ctx=SimpleNamespace(new_page=lambda:p)
  with patch.object(m,'time',clock),patch.object(m,'observe_visual_readiness',return_value=lambda:None),patch.object(m,'workflow_call',side_effect=lambda stage,fn,scope,*a,**kw:fn(*a,**kw)):
   m.capture_owned_md_page(run,result,None,ctx,deadline)
  self.assertEqual(result,original)
  return run,p,clock
 def test_observed_slow_bound_record_recovers_without_navigation_retry(self):
  r,p,c=self.run_case();self.assertEqual(len(r.documents),1);self.assertEqual(p.shots,1);self.assertEqual(p.clicks,1)
  self.assertTrue(r.visual_adapter_facts[0]['finish_allowance_after_bound_record']);self.assertLessEqual(c.now,135);self.assertTrue(p.closed)
 def test_healthy_path_has_no_extra_allowance_or_wait(self):
  r,p,c=self.run_case(nav=.5,panel_delay=.1);self.assertEqual(len(r.documents),1)
  self.assertNotIn('finish_allowance_extra_ms',r.visual_adapter_facts[0]);self.assertLess(c.now,102)
 def test_slow_ready_record_without_alert_can_finish(self):
  r,p,c=self.run_case(alert=False);self.assertEqual(len(r.documents),1);self.assertEqual(p.clicks,0)
 def test_wrong_name_identifier_or_status_never_gets_allowance(self):
  for fields in [{'Charity Name':'Other charity'},{'Charity ID':'999'},{'Registration Status':'Current'}]:
   with self.subTest(fields=fields):
    r,p,c=self.run_case(fields=fields);self.assertFalse(r.documents);self.assertEqual(p.shots,0);self.assertNotIn('finish_allowance_extra_ms',r.visual_adapter_facts[0])
 def test_wrong_ein_and_foreign_page_rejected(self):
  r,p,c=self.run_case(foreign_ein=True);self.assertFalse(r.documents);self.assertFalse(r.visual_adapter_facts)
  r,p,c=self.run_case(foreign_url=True);self.assertFalse(r.documents);self.assertNotIn('finish_allowance_extra_ms',r.visual_adapter_facts[0])
 def test_changed_record_during_alert_is_rejected(self):
  r,p,c=self.run_case(change_alert=True);self.assertFalse(r.documents);self.assertEqual(p.shots,0)
  self.assertEqual(r.visual_adapter_facts[0]['outcome'],'general_source_changed_during_alert')
 def test_changed_record_during_screenshot_is_rejected(self):
  r,p,c=self.run_case(change_shot=True);self.assertFalse(r.documents);self.assertEqual(p.shots,1)
 def test_verification_page_is_never_published(self):
  r,p,c=self.run_case(verification=True);self.assertFalse(r.documents);self.assertEqual(p.shots,0)
 def test_task_deadline_is_not_extended(self):
  r,p,c=self.run_case(deadline=130);self.assertFalse(r.documents);self.assertLess(c.now,130)
  self.assertNotIn('finish_allowance_extra_ms',r.visual_adapter_facts[0])
 def test_navigation_timeout_does_not_receive_allowance(self):
  r,p,c=self.run_case(nav=35);self.assertFalse(r.documents);self.assertEqual(p.shots,0)
  self.assertNotIn('finish_allowance_extra_ms',r.visual_adapter_facts[0]);self.assertLess(c.now,130)
 def test_alert_and_capture_hangs_remain_bounded(self):
  for opt in [dict(dismiss_delay=20),dict(shot_delay=20)]:
   with self.subTest(opt=opt):
    r,p,c=self.run_case(**opt);self.assertFalse(r.documents);self.assertLess(c.now,135)
 def test_allowance_cannot_be_revived_after_local_expiry(self):
  # Source API returns late despite its own timeout; no extension may revive it.
  original=Node.inner_text
  def late(node,timeout=None):
   if node.label=='Latest Approval Date':node.p.clock.spend(2)
   return original(node,timeout)
  with patch.object(Node,'inner_text',late):r,p,c=self.run_case()
  self.assertFalse(r.documents);self.assertNotIn('finish_allowance_extra_ms',r.visual_adapter_facts[0]);self.assertEqual(p.shots,0)

if __name__=='__main__':unittest.main()
