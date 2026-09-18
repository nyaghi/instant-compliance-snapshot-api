"""A completed Massachusetts empty query must not occupy discovery until timeout."""
import sys,time,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class CompletedEmptyDiscovery(unittest.TestCase):
    def run_page(self,body):
        manager=MagicMock();browser=manager.__enter__.return_value.chromium.launch.return_value
        page=browser.new_context.return_value.new_page.return_value
        page.locator.return_value.inner_text.return_value=body
        page.wait_for_timeout.side_effect=TimeoutError('No completed response; do not classify it as an empty search')
        with patch.object(c.checker,'sync_playwright',return_value=manager):
            result=c.identity_browser_names('MA','237091805',time.monotonic()+2)
        page.get_by_role.assert_any_call('button',name='Search',exact=True)
        browser.close.assert_called_once();return result
    def test_actual_singular_state_message_completes_without_waiting(self):
        result=self.run_page('Public Charities Filing Search\nSearch\nClear\nNo Charity Found.\nMassachusetts Office of the Attorney General')
        self.assertTrue(result['complete']);self.assertEqual(result['names'],[])
    def test_existing_plural_messages_still_complete(self):
        for message in ['No charities found','No records were found','No results found']:
            with self.subTest(message=message):self.assertTrue(self.run_page(message)['complete'])
    def test_loading_failure_or_general_instructions_are_not_empty_results(self):
        for body in ['Loading...','Search failed. Please try again.','This search will only return registered charities.','No charity filing date was found']:
            with self.subTest(body=body),self.assertRaises(TimeoutError):self.run_page(body)

if __name__=='__main__':unittest.main(verbosity=2)
