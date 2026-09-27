"""Verified transport experiment must retain every lookup and TLS decision."""
import ast
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m

class VerifiedFirst(unittest.TestCase):
    env={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com',
         'CE_LAB_FL_TRANSPORT':'verified-first'}

    def test_only_explicit_exact_lab_can_enable(self):
        for version,origin,mode,expected in [
            ('fixture-performance-lab',self.env['PUBLIC_BASE_URL'],'verified-first',True),
            ('fixture',self.env['PUBLIC_BASE_URL'],'verified-first',False),
            ('fixture-performance-lab','https://staging.compliance-express.com','verified-first',False),
            ('fixture-performance-lab',self.env['PUBLIC_BASE_URL'],'',False),
            ('fixture-performance-lab',self.env['PUBLIC_BASE_URL'],'typo',False)]:
            with self.subTest(version=version,origin=origin,mode=mode),patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':origin,'CE_LAB_FL_TRANSPORT':mode}):
                self.assertIs(m.fl_verified_transport_first(),expected)

    def test_first_navigation_uses_bounded_verified_transport_and_same_result(self):
        from testing.run_fl_navigation_deadline_guardrails import FloridaNavigationTests
        for no_record,wrong_name,expected in [(False,False,'Current'),(True,False,m.checker.STATUS_NOT_REGISTERED),(False,True,m.checker.STATUS_NOT_REGISTERED)]:
            with self.subTest(no_record=no_record,wrong_name=wrong_name),patch.object(m,'APP_VERSION','fixture-performance-lab'),patch.dict(os.environ,self.env):
                deadlines=[]
                def enable(t):deadlines.append(t.deadline);t.enabled=True
                with patch.object(m.FloridaVerifiedTransport,'enable',autospec=True,side_effect=enable):
                    result,visits,_,seconds=FloridaNavigationTests().run_case(failures=0,no_record=no_record,wrong_name=wrong_name)
                self.assertEqual(result.status,expected)
                self.assertTrue(result.success)
                self.assertEqual(len(deadlines),1);self.assertGreater(deadlines[0],0)
                self.assertEqual(visits[0][0],m.FL_CHECK_A_CHARITY_URL)
                self.assertLessEqual(visits[0][1]['timeout'],12000)
                if expected=='Current':self.assertEqual(result.matched_registry_identifier,'CH12345')

    def test_timeout_never_becomes_completed_negative(self):
        from testing.run_fl_navigation_deadline_guardrails import FloridaNavigationTests
        with patch.object(m,'APP_VERSION','fixture-performance-lab'),patch.dict(os.environ,self.env),patch.object(m.FloridaVerifiedTransport,'enable',autospec=True,side_effect=lambda t:setattr(t,'enabled',True)):
            result,_,_,seconds=FloridaNavigationTests().run_case(failures=10)
        self.assertFalse(result.success);self.assertNotEqual(result.status,m.checker.STATUS_NOT_REGISTERED)
        self.assertLess(seconds,50)

    def test_untrusted_first_transport_is_not_retried_insecurely(self):
        from testing.run_fl_navigation_deadline_guardrails import FloridaNavigationTests
        with patch.object(m,'APP_VERSION','fixture-performance-lab'),patch.dict(os.environ,self.env),patch.object(m.FloridaVerifiedTransport,'enable',side_effect=m.FloridaCertificateError('untrusted chain')):
            result,*_=FloridaNavigationTests().run_case(failures=0)
        self.assertFalse(result.success);self.assertEqual(result.reason_code,'FL_CERTIFICATE_ERROR')

    def test_remaining_master_is_identical_to_previous_release(self):
        from testing.capacity_lab.parsing_scope import strip_fl_verified_first_trial
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','669920c:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_fl_verified_first_trial(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_assets_use_browser_only_for_explicit_lab_experiment(self):
        for enabled in [False,True]:
            for resource in ['script','stylesheet','xhr','document','image']:
                with self.subTest(enabled=enabled,resource=resource),patch.object(m,'fl_verified_transport_first',return_value=enabled),patch.object(m,'BLOCK_HEAVY_BROWSER_RESOURCES',True):
                    route=MagicMock();route.request.url=m.FL_CHECK_A_CHARITY_URL
                    route.request.resource_type=resource;route.request.method='GET'
                    tr=m.FloridaVerifiedTransport(MagicMock());tr.deadline=0
                    tr.route(route)
                    if enabled and resource not in ['document','image']:
                        route.fallback.assert_called_once();route.abort.assert_not_called()
                    else:
                        route.fallback.assert_not_called();route.abort.assert_called_once()

if __name__=='__main__':unittest.main()
