"""Do not submit a truncated EIN; keep PA's confirmation and scoring rules."""
import ast
from contextlib import ExitStack
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch
import registry_snapshot_server as m


class PennsylvaniaReadyFormTests(unittest.TestCase):
    def run_search(self, maximum, rows=None):
        page=Mock();field=Mock();field.get_attribute.return_value=maximum
        with ExitStack() as stack:
            stack.enter_context(patch.object(m.checker,'safe_wait_for_network_idle'))
            stack.enter_context(patch.object(m.checker,'fast_sleep'))
            stack.enter_context(patch.object(m.checker,'find_pa_ein_input',return_value=field))
            click=stack.enter_context(patch.object(m.checker,'click_pa_search_button',return_value=True))
            extract=stack.enter_context(patch.object(m.checker,'extract_pa_result_expiration',side_effect=rows or [('', ''),('', '')]))
            r=m.checker.search_pa(page,m.checker.Organization('Example Relief','123456789'))
        return r,field,click,extract

    def test_nine_digit_field_does_not_submit_truncated_dashed_ein(self):
        r,field,click,extract=self.run_search('9')
        self.assertEqual(field.fill.call_args_list[-1].args,('123456789',))
        self.assertEqual(click.call_count,1);self.assertEqual(extract.call_count,1)
        self.assertEqual(m.public_status(r),'Not Registered')

    def test_capable_or_unspecified_field_retains_formatted_retry(self):
        for maximum in ('10','20','',None,'unknown'):
            r,field,click,extract=self.run_search(maximum)
            self.assertEqual(field.fill.call_args_list[-1].args,('12-3456789',))
            self.assertEqual(click.call_count,2);self.assertEqual(extract.call_count,2)

    def test_current_ein_match_never_enters_retry(self):
        r,field,click,extract=self.run_search('9',[('Example Relief 123456789 12/31/2027','12/31/2027')])
        self.assertEqual(m.public_status(r),'Current')
        field.get_attribute.assert_not_called();self.assertEqual(click.call_count,1)

    def test_only_complete_visible_same_portal_form_reuses_readiness(self):
        url='https://www.charities.pa.gov/#/page/searchCharities'
        for current,visible in ((url,True),(url,False),('https://other.example/',True)):
            page=Mock(url=current);page.locator.return_value.is_visible.return_value=visible
            page.get_by_role.return_value.first.is_visible.return_value=True
            with patch.object(m.checker,'safe_wait_for_network_idle') as idle,patch.object(m.time,'sleep'):
                m.pa_prepare_name_fallback_form(page,url)
            self.assertEqual(page.goto.call_count,0 if current==url and visible else 1)
            self.assertEqual(idle.call_count,page.goto.call_count)

    def test_only_retry_field_constraint_changed_in_shared_checker(self):
        root=Path(m.__file__).parent;name='Charity_Checker_Script for 13_states.py'
        old=ast.parse(subprocess.check_output(['git','show','88e5f17:'+name],cwd=root).decode())
        new=ast.parse((root/name).read_text(encoding='utf-8'))
        fn=next(n for n in new.body if getattr(n,'name','')=='search_pa')
        branch=next(n for n in ast.walk(fn) if isinstance(n,ast.If) and ast.unparse(n.test)=='retry_input')
        self.assertEqual(ast.unparse(branch.body[0]),"maximum = retry_input.get_attribute('maxlength') or ''")
        self.assertEqual(ast.unparse(branch.body[1].test),'not (maximum.isdigit() and len(formatted_ein) > int(maximum))')
        branch.body=branch.body[1].body
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_master_matching_completion_confirmation_and_other_states_unchanged(self):
        from testing.capacity_lab.parsing_scope import strip_pa_form_optimization
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','88e5f17:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        strip_pa_form_optimization(new)
        self.assertEqual(ast.dump(old),ast.dump(new))


if __name__=='__main__':unittest.main()
