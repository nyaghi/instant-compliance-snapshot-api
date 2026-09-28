"""Distinguish an unanswered verification request from explicit rejection."""
import ast,subprocess,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m
from testing.run_ny_retrieval_guardrails import ROW,DETAIL,response,AsOfDate

class VerificationTimeout(unittest.TestCase):
    def test_only_timeout_classification_changed_in_master(self):
        from testing.capacity_lab.ny_failed_scope import strip_ny_failed_wakeup
        root=Path(m.__file__).parent
        before=ast.parse(subprocess.check_output(['git','show','647fddb:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        after=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_ny_failed_wakeup(after)
        self.assertEqual(ast.dump(before),ast.dump(after))

    def page(self):
        p=MagicMock();p.url='https://charities-search.ag.ny.gov/RegistrySearch'
        p._cc_ny_search_url=None
        self.search=MagicMock();self.search.is_enabled.return_value=False
        p.get_by_role.side_effect=lambda role,**kw:self.search if kw.get('name')=='Search' else MagicMock()
        return p

    def test_unanswered_verification_retains_actual_timeout_type(self):
        for error in (TimeoutError('deadline'),m.checker.PlaywrightTimeoutError('verification response timed out')):
            p=self.page();p.expect_response.return_value.__enter__.side_effect=error
            with self.assertRaises(type(error)):
                m.ny_browser_registry_response(p,'RegistrySearch',{'ein':'123456789'},12)

    def test_accepted_verification_but_unready_search_retains_timeout(self):
        p=self.page();pending=p.expect_response.return_value.__enter__.return_value
        pending.value.status=200;pending.value.json.return_value={'verified':True}
        p.wait_for_function.side_effect=m.checker.PlaywrightTimeoutError('Search not ready')
        with self.assertRaises(m.checker.PlaywrightTimeoutError):
            m.ny_browser_registry_response(p,'RegistrySearch',{'ein':'123456789'},12)

    def test_explicit_rejection_remains_verification_required(self):
        for status,body in [(200,{'verified':False}),(403,{'verified':False}),(429,{'verified':False})]:
            p=self.page();pending=p.expect_response.return_value.__enter__.return_value
            pending.value.status=status;pending.value.json.return_value=body
            with self.assertRaises(m.NYVerificationRequired):
                m.ny_browser_registry_response(p,'RegistrySearch',{'ein':'123456789'},12)

    def test_actual_verification_timeout_uses_existing_one_retry(self):
        p=self.page();p.expect_response.return_value.__enter__.side_effect=m.checker.PlaywrightTimeoutError('slow verification')
        real=m.ny_browser_registry_response;calls=[]
        def transport(page,operation,params,timeout):
            calls.append((operation,params,timeout))
            if len(calls)==1:return real(page,operation,params,timeout)
            return response([ROW]) if operation=='RegistrySearch' else response(DETAIL)
        org=m.checker.Organization('Example National Foundation','123456789')
        with patch.object(m,'ny_browser_registry_response',side_effect=transport),patch.object(m.time,'sleep'),patch.object(m,'date',AsOfDate):
            result=m.search_ny_direct(org,browser_page=p)
        self.assertTrue(result.success);self.assertEqual(len(calls),3)
        self.assertEqual(calls[0][:2],calls[1][:2])
        self.assertTrue(any('retrying transient' in x for x in result.source_attempts))

    def test_explicit_rejection_is_not_retried(self):
        org=m.checker.Organization('Example National Foundation','123456789')
        with patch.object(m,'ny_browser_registry_response',side_effect=m.NYVerificationRequired('rejected')) as lookup:
            result=m.search_ny_direct(org,browser_page=self.page())
        self.assertFalse(result.success);self.assertEqual(lookup.call_count,1)
        self.assertEqual(result.status_reason,'NY_VERIFICATION_REQUIRED')

if __name__=='__main__':unittest.main(verbosity=2)
