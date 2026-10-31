"""Successful retained evidence completes the existing automatic close capture."""
import unittest,time
from unittest.mock import MagicMock,patch
from deployment import state_snapshots as ss,source_visual_adapters as adapters,fl_response_evidence as fl
import registry_snapshot_server as master

class FloridaContextCompletion(unittest.TestCase):
    def workflow(self,index,outcome=True,state='FL',valid=True):
        run=ss.CaptureRun('Example Relief '+str(index),str(100000000+index),state)
        raw=MagicMock();raw.pages=[MagicMock()];token=ss.CURRENT.set(run)
        try:
            proxy=ss.ContextCaptureProxy(raw)
            row={'state':state,'ein':run.ein,'success':True,'status':'Current','source_url':fl.URL,
                 'matched_registry_name':run.name,'matched_registry_identifier':'CH'+str(50000+index)}
            if not valid:row['ein']='999999999'
            with patch.object(fl,'capture',return_value=outcome),patch.object(run,'page') as page_capture:
                proxy._context.pages[0].goto.side_effect=RuntimeError('modeled source unavailable')
                adapters.capture_owned_fl_page(master,run,row,proxy._context.pages[0],proxy,time.monotonic()+30)
                proxy.close()
                return page_capture.call_count,proxy._captured,raw.close.call_count
        finally:ss.CURRENT.reset(token)

    def test_thirty_successful_retained_images_are_not_recaptured_on_close(self):
        for index in range(30):
            with self.subTest(index=index):self.assertEqual(self.workflow(index),(0,True,1))

    def test_thirty_failed_or_rejected_retained_captures_preserve_close_fallback(self):
        for index in range(30):
            self.assertEqual(self.workflow(index,outcome=False),(1,True,1))
            self.assertEqual(self.workflow(index,valid=False),(1,True,1))

    def test_other_state_context_close_remains_unchanged(self):
        for index in range(30):
            for state in ['CO','NY','WI','IL','NC','TN','MS','GA']:
                self.assertEqual(self.workflow(index,state=state),(1,True,1))

if __name__=='__main__':unittest.main()
