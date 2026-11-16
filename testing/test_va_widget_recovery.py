import copy,json,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from deployment import source_visual_adapters as a

FACT=json.loads((Path(__file__).parent/'fixtures/fresh-five/VA-USO-WIDGET-STALL.json').read_text())
class TimeoutError(Exception):pass

class WidgetRecovery(unittest.TestCase):
 def test_saved_stall_and_guards(self):
  self.assertTrue(a.va_widget_initialization_stalled(FACT))
  for key,value in [('expected_id_present',False),('expected_name_present',False),('form_count',1),
                    ('verification_present',True),('error_present',True),('document_state','loading')]:
   f=copy.deepcopy(FACT);f['selected_readiness_observation']['terminal'][key]=value
   self.assertFalse(a.va_widget_initialization_stalled(f),key)
  for key,value in [('route_matches',False),('failed',1),('errors',['failure']),('pending_overflow',1)]:
   f=copy.deepcopy(FACT);f['selected_readiness_observation'][key]=value
   self.assertFalse(a.va_widget_initialization_stalled(f),key)
  for change in [{'status':200},{'host':'other.example'},{'age_seconds':1},{'path':'/unrelated.js'}]:
   f=copy.deepcopy(FACT);f['selected_readiness_observation']['pending'][1].update(change)
   self.assertFalse(a.va_widget_initialization_stalled(f),change)
 def test_reloads_only_the_same_selected_url_once_within_original_stop(self):
  f=copy.deepcopy(FACT);page=Mock(url='https://vdacs.evokeplatform.com/app/publicPortal/registration/123')
  page.get_by_role.return_value.wait_for.side_effect=[TimeoutError(),None]
  page.reload.return_value=SimpleNamespace(status=200);clock=[0]
  def checkpoint():clock[0]=15
  with patch.object(a.time,'monotonic',lambda:clock[0]):
   a.wait_va_selected_heading(page,f,checkpoint,page.url,30)
  page.reload.assert_called_once_with(wait_until='commit',timeout=5000)
  self.assertEqual(page.get_by_role.return_value.wait_for.call_args_list[-1].kwargs['timeout'],14000)
  self.assertFalse(a.va_widget_initialization_stalled(f));page.goto.assert_not_called()
 def test_healthy_page_does_not_reload_or_wait_extra(self):
  p=Mock();f={};checkpoint=Mock()
  a.wait_va_selected_heading(p,f,checkpoint,'url',time.monotonic()+30)
  p.reload.assert_not_called();checkpoint.assert_not_called()
 def test_rejected_reload_never_becomes_evidence(self):
  for status in [403,429,503]:
   p=Mock(url='url');p.get_by_role.return_value.wait_for.side_effect=TimeoutError()
   p.reload.return_value=SimpleNamespace(status=status)
   with self.assertRaises(ValueError):a.wait_va_selected_heading(p,copy.deepcopy(FACT),lambda:None,'url',time.monotonic()+30)

if __name__=='__main__':unittest.main()
