"""A missing Michigan results frame is retryable, not a completed negative."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class MichiganMissingFrameControls(unittest.TestCase):
    def incomplete(self):
        return {'status':'Unable to Verify','success':False,'reason_code':'MI_NAME_SEARCH_INCOMPLETE',
                'raw_status_text':'Michigan organization-name search did not complete',
                'source_note':'Michigan did not expose a completed name-results frame. No negative registration conclusion was drawn.',
                'error':''}

    def test_missing_results_frame_is_retryable_without_timeout_word(self):
        self.assertTrue(c.mi_transient_lookup_result(self.incomplete()))

    def test_other_incomplete_evidence_does_not_get_transport_retry(self):
        for message in ['No usable organization-name query was available after the EIN search.',
                        'Michigan returned an unrecognized name-results page.',
                        'The matched Michigan record did not expose status evidence.']:
            with self.subTest(message=message):
                row=self.incomplete();row['source_note']=message
                self.assertFalse(c.mi_transient_lookup_result(row))

    def test_existing_explicit_timeout_still_retries(self):
        row=self.incomplete();row.update(source_note='Name search time budget ended.',error='Timeout 12000ms exceeded')
        self.assertTrue(c.mi_transient_lookup_result(row))

    def invoke(self,effects):
        with patch.object(c,'run_state_lookup',side_effect=effects) as lookup, \
             patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS',2), \
             patch.object(c,'SINGLE_STATE_SEMANTIC_RETRY_DELAY_SECONDS',0):
            result=c.run_single_state_lookup_reliably('Frame Recovery Control','12-3456789','MI')
        return result,lookup

    def test_retry_retains_completed_ein_and_name_progress(self):
        progress_ids=[]
        def lookup(name,ein,state,mi_progress):
            progress_ids.append(id(mi_progress))
            if len(progress_ids)==1:
                mi_progress['completed_empty_ein_result']='verified-empty-ein'
                mi_progress['completed_empty_name_queries']=['Frame Recovery Control, Inc.']
                return self.incomplete()
            self.assertEqual(mi_progress['identity'],('Frame Recovery Control','123456789'))
            self.assertEqual(mi_progress['completed_empty_ein_result'],'verified-empty-ein')
            self.assertEqual(mi_progress['completed_empty_name_queries'],['Frame Recovery Control, Inc.'])
            return {'status':'Not Registered','success':True,'reason_code':'MI_COMPLETED_EIN_AND_NAME_SEARCH'}
        result,mocked=self.invoke(lookup)
        self.assertEqual(mocked.call_count,2);self.assertEqual(len(set(progress_ids)),1)
        self.assertEqual(result['status'],'Not Registered');self.assertEqual(result['semantic_attempts'],2)

    def test_persistent_missing_frame_remains_inconclusive_after_bound(self):
        result,mocked=self.invoke([self.incomplete(),self.incomplete()])
        self.assertEqual(mocked.call_count,2);self.assertEqual(result['status'],'Unable to Verify')
        self.assertFalse(result['success'])

    def test_completed_success_or_negative_does_not_repeat(self):
        for status,reason in [('Current','MATCH_EIN_EXACT'),('Not Registered','MI_COMPLETED_EIN_AND_NAME_SEARCH')]:
            with self.subTest(status=status):
                result,mocked=self.invoke([{'status':status,'success':True,'reason_code':reason}])
                self.assertEqual(mocked.call_count,1);self.assertEqual(result['status'],status)

if __name__=='__main__':unittest.main(verbosity=2)
