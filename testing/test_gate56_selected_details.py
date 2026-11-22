import json
import pathlib
import unittest
from unittest.mock import Mock
from types import SimpleNamespace

from deployment import source_visual_adapters as adapters

ROOT = pathlib.Path(__file__).parent
WIDGET = '/api/webContent/plugins/out-of-the-box-widgets/files/'


class SelectedDetails(unittest.TestCase):
    def test_seventy_record_bindings_and_bounded_repairs(self):
        records = json.loads((ROOT/'fixtures/gate55/LOCAL-70.json').read_text())
        self.assertEqual(len({row['ein'] for row in records}), 70)
        for row in records:
            for blank in (True, False):
                with self.subTest(ein=row['ein'], blank=blank):
                    url = 'https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/' + row['ein']
                    page = Mock(url=url)
                    page.evaluate.return_value = blank
                    page.reload.return_value = SimpleNamespace(status=200)
                    locator = Mock()
                    locator.wait_for.side_effect = [TimeoutError(), None]
                    adapters.wait_ca_exempt_status(page, locator, url, lambda: 12000, {})
                    self.assertEqual(page.reload.call_count, int(blank))
                    self.assertEqual(locator.wait_for.call_count, 2)
                    page.goto.assert_not_called()
            def asset(name):
                return dict(type='script', host='vdacs.evokeplatform.com', path=WIDGET+name+'.js')
            original, current = asset('61'), asset('285')
            observation = dict(route_matches=True, terminal_read='completed', pending_overflow=0,
                               failed=1, failures=[dict(original, code='net::ERR_ABORTED')], pending=[current],
                               terminal=dict(body_text_chars=0, form_count=0, document_state='complete',
                                             verification_present=False, error_present=False))
            fact = dict(widget_initialization_reload={'count':1}, widget_initialization_boundary={'pending':[original]},
                        selected_readiness_observation=observation)
            with self.subTest(ein=row['ein']):
                self.assertEqual(adapters.va_reloaded_widget_stop(fact, 30, 300, 29), 40)
                self.assertIsNone(adapters.va_reloaded_widget_stop(fact, 30, 34, 29))
                for change in (dict(failed=2), dict(route_matches=False), dict(pending=[original]),
                               dict(pending=[dict(current, host='other.example')])):
                    self.assertIsNone(adapters.va_reloaded_widget_stop(dict(fact, selected_readiness_observation=dict(observation, **change)), 30, 300, 29))
        locator=Mock()
        page=Mock()
        adapters.wait_ca_exempt_status(page,locator,'healthy',lambda:29000,{})
        page.evaluate.assert_not_called()
        page.reload.assert_not_called()

