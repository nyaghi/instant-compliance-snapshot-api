"""A pending or failed Oregon AJAX response is never a registration negative."""
import ast
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m


class OregonCompletion(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(m,'APP_VERSION','fixture-performance-lab'))
        self.stack.enter_context(patch.dict(m.os.environ,{'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com'}))
        self.org=SimpleNamespace(organization_name='Example Relief',ein='123456789')
        self.page=MagicMock();self.body='<table><tr><td>Example Relief</td></tr></table>'
        self.request=SimpleNamespace(url='https://justice.oregon.gov/Charities/Charity/Results',method='POST',post_data='Name=Example+Relief&EIN=')
        self.response=MagicMock(status=200);self.response.text.return_value=self.body
        self.request.response=lambda:self.response
        self.page.expect_event.return_value.__enter__.return_value.value=self.request
        self.module=SimpleNamespace(search_or=self.search)
        self.result=SimpleNamespace(status='Current',success=True,raw_status_text='Registered',source_note='Original rule',error='')
    def search(self,page,org):
        try:page.locator('#search').click(timeout=10000)
        except Exception:return SimpleNamespace(status='Unknown',success=False,raw_status_text='',source_note='',error='Bundled error')
        return self.result
    def test_complete_query_waits_for_body_and_dom_then_preserves_result(self):
        self.assertIs(m.search_or_completed(self.page,self.org,self.module),self.result)
        args=self.page.expect_event.call_args
        self.assertEqual(args.args,('requestfinished',))
        self.assertTrue(args.kwargs['predicate'](self.request))
        self.assertEqual(self.page.wait_for_function.call_args.kwargs['arg'],self.body)
        self.assertLessEqual(self.page.wait_for_function.call_args.kwargs['timeout'],10000)
    def test_matching_event_requires_official_origin_path_method_name_and_no_ein_filter(self):
        m.search_or_completed(self.page,self.org,self.module)
        predicate=self.page.expect_event.call_args.kwargs['predicate']
        for changes in [{'url':'https://other.example/Charities/Charity/Results'},
                        {'url':'https://justice.oregon.gov/other'}, {'method':'GET'},
                        {'post_data':'Name=Other&EIN='}, {'post_data':'Name=Example+Relief&EIN=987654321'},
                        {'post_data':'Name=Example+Relief&Name=Other&EIN='}]:
            self.assertFalse(predicate(SimpleNamespace(**{**self.request.__dict__,**changes})))
    def test_incomplete_transport_or_dom_cannot_be_a_negative(self):
        for target in ['expect_event','wait_for_function']:
            page=MagicMock();page.expect_event.return_value.__enter__.return_value.value=self.request
            getattr(page,target).side_effect=TimeoutError('unfinished')
            result=m.search_or_completed(page,self.org,self.module)
            self.assertEqual(result.status,'Unable to Verify');self.assertFalse(result.success)
            self.assertEqual(result.reason_code,'OR_INCOMPLETE_QUERY_RESPONSE')
    def test_invalid_responses_cannot_be_classified(self):
        for code,body in [(503,self.body),(200,''),(200,'Verify you are human'),(200,'x'*1_000_001)]:
            self.response.status=code;self.response.text.return_value=body
            result=m.search_or_completed(self.page,self.org,self.module)
            self.assertFalse(result.success);self.assertEqual(result.reason_code,'OR_INCOMPLETE_QUERY_RESPONSE')
    def test_completed_negative_keeps_original_rule(self):
        self.result.status='Not Registered';self.response.text.return_value='<div>No record found</div>'
        result=m.search_or_completed(self.page,self.org,self.module)
        self.assertIs(result,self.result);self.assertTrue(result.success)
    def test_no_search_event_is_not_success(self):
        self.module.search_or=lambda page,org:self.result
        result=m.search_or_completed(self.page,self.org,self.module)
        self.assertFalse(result.success);self.assertEqual(result.status,'Unable to Verify')
    def test_nonlab_uses_original_page_without_wrapper(self):
        for version,url in [('production','https://instant-compliance-snapshot-api-hn4v.onrender.com'),
                            ('v-performance-lab','https://staging.compliance-express.com')]:
            fn=MagicMock(return_value=self.result)
            with patch.object(m,'APP_VERSION',version),patch.dict(m.os.environ,{'PUBLIC_BASE_URL':url}):
                self.assertIs(m.search_or_completed(self.page,self.org,SimpleNamespace(search_or=fn)),self.result)
            fn.assert_called_once_with(self.page,self.org)
    def test_parser_matching_and_filing_rules_are_unchanged(self):
        from testing.capacity_lab.or_completion_scope import strip_or_completion
        tree=ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        strip_or_completion(tree)


if __name__=='__main__':unittest.main()
