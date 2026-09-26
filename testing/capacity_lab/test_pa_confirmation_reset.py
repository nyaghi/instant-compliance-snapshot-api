"""A same-route PA confirmation must clear the preceding name/address filters."""
import ast
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock,patch
import registry_snapshot_server as c
from testing.run_ny_lab_readiness_guardrails import ReadinessTests


class PennsylvaniaReset(unittest.TestCase):
    def test_prior_name_and_address_filters_are_cleared_before_ein_submission(self):
        state={'name':'Former Name','city':'Previous City','ein':''}
        page=Mock();field=Mock();field.get_attribute.return_value='9'
        field.fill.side_effect=lambda value:state.update(ein=value)
        def clear(**kwargs):
            self.assertEqual(kwargs,{'timeout':1500});state.update(name='',city='',ein='')
        page.get_by_role.return_value.first.click.side_effect=clear
        def search(p):
            self.assertEqual(state,{'name':'','city':'','ein':'123456789'});return True
        with patch.object(c.checker,'safe_wait_for_network_idle'),patch.object(c.checker,'fast_sleep'),patch.object(c.checker,'find_pa_ein_input',return_value=field),patch.object(c.checker,'click_pa_search_button',side_effect=search),patch.object(c.checker,'extract_pa_result_expiration',return_value=('','')):
            r=c.checker.search_pa(page,c.checker.Organization('Control Foundation','123456789'),wait_for_ein=lambda ein:True)
        self.assertEqual(c.public_status(r),'Not Registered')
        page.get_by_role.return_value.first.click.assert_called_once()

    def test_failed_reset_cannot_submit_or_create_negative(self):
        page=Mock();page.get_by_role.return_value.first.click.side_effect=c.checker.PlaywrightTimeoutError('reset failed')
        with patch.object(c.checker,'safe_wait_for_network_idle'),patch.object(c.checker,'fast_sleep'),patch.object(c.checker,'find_pa_ein_input',return_value=Mock()),patch.object(c.checker,'click_pa_search_button') as search,patch.object(c.checker,'extract_pa_result_expiration') as read:
            r=c.checker.search_pa(page,c.checker.Organization('Control Foundation','123456789'))
        search.assert_not_called();read.assert_not_called();self.assertFalse(r.success)
        self.assertNotEqual(c.public_status(r),'Not Registered')

    def test_entire_engine_only_changes_reset_and_http_code_diagnostic(self):
        from testing.capacity_lab.parsing_scope import strip_pa_reset_and_ny_http_diagnostic
        root=Path(c.__file__).parent
        for name in ('registry_snapshot_server.py','Charity_Checker_Script for 13_states.py'):
            before=ast.parse(subprocess.check_output(['git','show','0a8c89e:'+name],cwd=root).decode('utf-8'))
            after=ast.parse((root/name).read_text(encoding='utf-8'));strip_pa_reset_and_ny_http_diagnostic(after)
            self.assertEqual(ast.dump(before),ast.dump(after))


class NewYorkHttpDiagnostic(ReadinessTests):
    def test_http_status_is_preserved_without_message_or_retry(self):
        for status in (403,429,500,502,503,504):
            self.page.goto.reset_mock();self.page.goto.return_value=Mock(status=status)
            r=self.run_lookup()
            self.assertIn(f'NY page navigation: HTTP {status}',r.source_attempts)
            self.page.goto.assert_called_once();self.direct.assert_not_called()
            self.assertFalse(r.success)


if __name__=='__main__':unittest.main(verbosity=2)
