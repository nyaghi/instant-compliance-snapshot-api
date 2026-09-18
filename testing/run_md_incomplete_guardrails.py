"""Exercise the master's Maryland branch with completed and failed responses."""
import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class MarylandCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(Path(c.__file__).read_text(encoding='utf-8'))
        run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_state_lookup')
        branch=next(n for n in ast.walk(run) if isinstance(n,ast.If)
            and ast.unparse(n.test)=="state == 'MD'"
            and any('checker.search_md' in ast.unparse(x) for x in n.body))
        wrapper=ast.parse('def run_branch(page, org, capture_source_snapshot=False):\n    pass\n').body[0]
        wrapper.body=branch.body+[ast.parse('return result, body').body[0]]
        ns=dict(vars(c));exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'master-md-branch','exec'),ns)
        cls.branch=staticmethod(ns['run_branch']);cls.ns=ns

    def run_response(self,result,matched=False):
        empty=Mock(return_value='Completed empty search');detail=Mock(return_value='Matched detail')
        with patch.object(c.checker,'search_md',return_value=result),patch.dict(self.ns,{
            'registry_page_body':lambda page:'Observed registry body',
            'md_detail_page_matched':lambda result,body:matched,
            'md_no_results_body':empty,'md_detail_body':detail,
            'repair_md_current_from_fiscal_due':lambda result,org,body:result}):
            answer,body=self.branch(Mock(),c.checker.Organization('Example Charity','12-3456789'))
        return answer,body,empty,detail

    def result(self,status,success,error=''):
        r=c.checker.StateResult('Example Charity','12-3456789','MD',status,'https://onestop.md.gov/',success=success)
        r.error=error;r.raw_status_text=status
        return r

    def test_navigation_errors_remain_failed_and_do_not_inspect_empty_results(self):
        for error in ['Page.goto: net::ERR_TOO_MANY_REDIRECTS','Page.goto: Timeout 15000ms exceeded','Connection closed']:
            for success in [False,True]:
                with self.subTest(error=error,success=success):
                    result,body,empty,detail=self.run_response(self.result('Unknown',success,error))
                    self.assertEqual(result.status,'Site Not Reachable');self.assertFalse(result.success)
                    self.assertEqual(result.error,error);self.assertNotIn('No matching EIN',result.raw_status_text)
                    empty.assert_not_called();detail.assert_not_called()

    def test_incomplete_response_without_exception_is_not_a_negative(self):
        result,_,empty,detail=self.run_response(self.result('Unknown',False))
        self.assertEqual(result.status,'Site Not Reachable');self.assertFalse(result.success)
        empty.assert_not_called();detail.assert_not_called()

    def test_completed_empty_search_is_preserved(self):
        result,_,empty,_=self.run_response(self.result(c.checker.STATUS_NOT_REGISTERED,True))
        self.assertEqual(c.public_status(result),'Not Registered');self.assertTrue(result.success)
        empty.assert_called_once()

    def test_confirmed_record_and_status_are_preserved(self):
        for status in ['Current','Delinquent','Pending','Suspended','Closed']:
            with self.subTest(status=status):
                result,_,empty,detail=self.run_response(self.result(status,True),matched=True)
                self.assertEqual(result.status,status);self.assertTrue(result.success)
                empty.assert_not_called();detail.assert_called_once()

if __name__=='__main__':unittest.main()
