import sys,unittest,copy,time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,MagicMock,patch
W=Path(__file__).resolve().parents[1];sys.path.insert(0,str(W))
from deployment import source_visual_adapters as v,gates2930_repairs as g,ca_accepted_renewal as ca
from testing.test_gates22_23_capture_budget import fixture_image
class Clock:
 now=100
 def monotonic(self):return self.now
 perf_counter=monotonic
 def spend(self,n,timeout):
  if n>timeout/1000:self.now+=timeout/1000;raise TimeoutError('fixture')
  self.now+=n
class SC(unittest.TestCase):
 def execute(self,baseline=False,nav=13,search=2,deadline=200,wrong_id=False,http=200,hang=False):
  clock=Clock();name='Example Relief Foundation';url='https://search.scsos.com/charities';body=name+'\nPublic Id: '+('P999' if wrong_id else 'P123')+'\nStatus: Registered'
  result=dict(state='SC',ein='123456789',success=True,status='Current',matched_registry_name=name,matched_registry_identifier='P123',source_url=url)
  run=NS(state='SC',ein='123456789',documents=[],visual_adapter_facts=[])
  page=Mock(url=url);link=Mock();panel=Mock();heading=Mock()
  link.filter.return_value=link;link.count.return_value=1;link.inner_text.return_value=name
  link.wait_for.side_effect=lambda **kw:clock.spend(search,kw['timeout']);link.click.side_effect=lambda **kw:clock.spend(.5,kw['timeout'])
  panel.locator.return_value=heading;heading.count.return_value=1;heading.inner_text.return_value=name
  panel.inner_text.return_value=body;panel.wait_for.side_effect=lambda **kw:clock.spend(1,kw['timeout'])
  page.locator.side_effect=lambda sel:link if sel.startswith('a[')else panel if 'Panel_CharityDetail'in sel else Mock()
  def go(*a,**kw):clock.spend(nav,kw['timeout']);return NS(status=http)
  page.goto.side_effect=go
  ctx=Mock();ctx.new_page.return_value=page
  def capture():
   clock.spend(10 if hang else .5,max(1,int((min(deadline,121)-clock.now)*1000)));run.documents.append({'sha256':'fixture','public_text':body,'url':url})
  ctx.capture.side_effect=capture;browser=Mock();browser.new_context.return_value=ctx
  master=NS(BROWSER_LOOKUP_SEMAPHORE=Mock(),checker=NS(sync_playwright=MagicMock()),launch_lookup_browser=Mock(return_value=browser))
  master.BROWSER_LOOKUP_SEMAPHORE.acquire.return_value=True
  with patch.object(v,'time',clock),patch.object(v,'workflow_call',side_effect=lambda stage,fn,scope,*a,**kw:fn(*a,**kw)),patch.object(g,'sc_finish_deadline',side_effect=(lambda stop,deadline,now:stop)if baseline else g.sc_finish_deadline):
   v.capture_selected_sc_source(master,result,run,deadline)
  self.assertTrue(ctx.close.called);self.assertTrue(master.BROWSER_LOOKUP_SEMAPHORE.release.called)
  return run,clock
 def test_late_successful_navigation_recovers(self):
  old,_=self.execute(baseline=True);new,clock=self.execute()
  self.assertFalse(old.documents);self.assertEqual(len(new.documents),1);self.assertLess(clock.now,121)
 def test_healthy_unchanged(self):
  for baseline in [True,False]:
   run,clock=self.execute(baseline=baseline,nav=1);self.assertEqual(len(run.documents),1);self.assertEqual(run.visual_adapter_facts[0]['finish_allowance_ms'],0)
 def test_observed_ten_second_navigation_then_slow_selected_link(self):
  old,_=self.execute(baseline=True,nav=10,search=5);new,clock=self.execute(nav=10,search=5)
  self.assertFalse(old.documents);self.assertEqual(len(new.documents),1);self.assertLess(clock.now,121)
 def test_no_extension_after_failure_or_expiry(self):
  for opts in [{'nav':17},{'http':503},{'wrong_id':True},{'deadline':116}]:
   with self.subTest(opts=opts):run,clock=self.execute(**opts);self.assertFalse(run.documents)

class CA(unittest.TestCase):
 def test_actual_visible_period_text_and_changed_ein(self):
  D=Path(__file__).resolve().parent/'fixtures/gates29-30';text=(D/'CA-RENEWAL-VISIBLE.txt').read_text(encoding='utf-8')
  proof=dict(url='https://ca-rcf.evokeplatform.com/app/publicPortal/requestDetailsRenewal/0JjR16KMjbKuZsx9OeyzC',name='LUTHERAN WORLD RELIEF INC.',registration='078450',ein='132574963',period_start='2024-10-01',period_end='2025-09-30')
  for changed in [False,True]:
   page=Mock(url=proof['url']);page.goto.return_value=NS(status=200);page.inner_text.side_effect=[text,text.replace('13-2574963','99-9999999') if changed else text]
   node=Mock();page.get_by_text.return_value=node;node.locator.return_value=node;node.bounding_box.return_value={'y':2335,'height':72};page.screenshot.return_value=fixture_image('Offline source binding fixture')
   run=NS(documents=[]);run.document=lambda *a,**kw:run.documents.append((a,kw));fact={}
   ca.capture_renewal(page,run,proof,time.monotonic()+30,fact)
   self.assertEqual(len(run.documents),0 if changed else 1,fact)
   self.assertLessEqual(page.screenshot.call_args.kwargs['clip']['height'],2435)
if __name__=='__main__':unittest.main(verbosity=2)
