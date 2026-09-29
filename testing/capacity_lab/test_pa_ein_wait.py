"""Delayed EIN response, exact request binding and unchanged PA interpretation."""
import ast, subprocess, unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import registry_snapshot_server as c
from testing.run_pa_completion_guardrails import Page, ORG, result

class PennsylvaniaEinWait(unittest.TestCase):
    def run_wait(self, setup, allowance=12):
        page=Page();out={}
        def core(p,org,guard,wait,offset):
            setup(p,offset,out)
            out['row']=wait('',out['offset'],p.clock+allowance,ein='123456789')
            out['elapsed']=p.clock
            return result('Current')
        with patch.object(c,'search_pa_with_name_fallback_core',side_effect=core),patch.object(c.time,'monotonic',side_effect=lambda:page.clock):
            c.search_pa_with_name_fallback(page,ORG)
        self.assertFalse(page.listeners)
        return out

    def test_slow_exact_ein_response_is_awaited(self):
        def setup(p,offset,out):
            out['offset']=offset();p.emit(payload={'Table':[{'EIN':'12-3456789'}]},delay=6)
        out=self.run_wait(setup)
        self.assertTrue(out['row']['complete']);self.assertEqual(out['row']['row_eins'],['123456789'])
        self.assertGreaterEqual(out['elapsed'],6);self.assertLess(out['elapsed'],6.2)

    def test_completed_empty_response_returns_without_sleeping_full_window(self):
        def setup(p,offset,out):out['offset']=offset();p.emit(delay=.2)
        out=self.run_wait(setup);self.assertEqual(out['row']['row_count'],0)
        self.assertLess(out['elapsed'],.4)

    def test_old_same_ein_different_ein_or_name_filter_cannot_complete_query(self):
        def setup(p,offset,out):
            p.emit();out['offset']=offset();p.emit(ein='987654321');p.emit(name='Other Foundation')
            p.emit(complete=False)
        out=self.run_wait(setup);self.assertFalse(out['row']);self.assertAlmostEqual(out['elapsed'],12,places=2)

    def test_late_response_is_not_accepted(self):
        def setup(p,offset,out):out['offset']=offset();p.emit(delay=13)
        out=self.run_wait(setup);self.assertFalse(out['row']);self.assertAlmostEqual(out['elapsed'],12,places=2)

    def test_error_response_ends_wait(self):
        def setup(p,offset,out):out['offset']=offset();p.emit(status=503,delay=.2)
        out=self.run_wait(setup);self.assertFalse(out['row']);self.assertLess(out['elapsed'],.4)

    def test_reader_runs_only_after_completed_ein_response(self):
        for complete in (True,False):
            page=MagicMock();ready=[]
            def wait(ein):self.assertEqual(ein,'123456789');ready.append(complete);return complete
            def extract(*args):
                self.assertEqual(ready,[True])
                return 'Completion Control Foundation 123456789 12/31/2027','12/31/2027'
            with patch.object(c.checker,'safe_wait_for_network_idle'),patch.object(c.checker,'fast_sleep'),patch.object(c.checker,'find_pa_ein_input',return_value=MagicMock()),patch.object(c.checker,'click_pa_search_button',return_value=True),patch.object(c.checker,'extract_pa_result_expiration',side_effect=extract) as read:
                r=c.checker.search_pa(page,ORG,wait_for_ein=wait)
            self.assertEqual(read.call_count,int(complete))
            if complete:self.assertEqual(c.public_status(r),'Current')
            else:
                self.assertFalse(r.success);self.assertEqual(r.reason_code,'PA_INCOMPLETE_SEARCH')
                self.assertNotEqual(c.public_status(r),'Not Registered')

    def test_scope_preserves_entire_other_master_and_checker_logic(self):
        from testing.capacity_lab.parsing_scope import strip_pa_ein_wait_and_ny_browser_timeout,strip_checker_pa_ein_wait
        root=Path(c.__file__).parent
        for name,strip in [('registry_snapshot_server.py',strip_pa_ein_wait_and_ny_browser_timeout),('Charity_Checker_Script for 13_states.py',strip_checker_pa_ein_wait)]:
            before=ast.parse(subprocess.check_output(['git','show','e9d6b9a:'+name],cwd=root).decode())
            after=ast.parse((root/name).read_text(encoding='utf-8'));strip(after)
            self.assertEqual(ast.dump(before),ast.dump(after))

if __name__=='__main__':unittest.main(verbosity=2)
