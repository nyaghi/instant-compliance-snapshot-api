"""Causal transport recovery control prepared before application changes."""
import ast,subprocess,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from email.message import Message
import registry_snapshot_server as m

class Recovery(unittest.TestCase):
    def request(self):
        route=MagicMock()
        route.request.url=m.FL_CHECK_A_CHARITY_URL
        route.request.resource_type='document';route.request.method='GET'
        route.request.post_data_buffer=None;route.request.all_headers.return_value={}
        return route

    def transport(self):
        tr=m.FloridaVerifiedTransport(MagicMock());tr.enabled=True;tr.deadline=time.monotonic()+30
        tr.opener=MagicMock()
        response=MagicMock();response.status=200;response.headers=Message()
        response.headers['Content-Type']='text/html';response.read1.side_effect=[b'<html>Fresh complete response</html>',b'']
        response.__enter__.return_value=response
        tr.opener.open.return_value=response
        return tr

    def test_successful_new_document_is_not_poisoned_by_prior_timeout(self):
        tr=self.transport();failed=self.request();fresh=self.request()
        response=tr.opener.open.return_value
        tr.opener.open.side_effect=[TimeoutError('prior incomplete navigation'),response]
        with patch.object(m,'fl_verified_transport_first',return_value=True):
            tr.route(failed);self.assertIsInstance(tr.error,TimeoutError)
            tr.route(fresh)
        failed.abort.assert_called_once();fresh.fulfill.assert_called_once()
        self.assertIsNone(tr.error,'A fully received fresh document still carries the previous transport timeout')

    def test_new_failure_remains_explicit(self):
        tr=self.transport();tr.error=TimeoutError('old timeout');route=self.request()
        tr.opener.open.side_effect=TimeoutError('new timeout')
        with patch.object(m,'fl_verified_transport_first',return_value=True):tr.route(route)
        self.assertEqual(str(tr.error),'new timeout');route.abort.assert_called_once();route.fulfill.assert_not_called()

    def test_deadline_stays_bounded(self):
        tr=self.transport();tr.error=TimeoutError('old timeout');tr.deadline=0;route=self.request()
        with patch.object(m,'fl_verified_transport_first',return_value=True):tr.route(route)
        self.assertIsInstance(tr.error,TimeoutError);tr.opener.open.assert_not_called();route.fulfill.assert_not_called()

    def test_certificate_failure_is_never_cleared(self):
        tr=self.transport();error=m.FloridaCertificateError('untrusted certificate');tr.error=error
        with patch.object(m,'fl_verified_transport_first',return_value=True):tr.route(self.request())
        self.assertIs(tr.error,error)

    def test_default_mode_unchanged(self):
        tr=self.transport();error=TimeoutError('earlier request');tr.error=error
        with patch.object(m,'fl_verified_transport_first',return_value=False):tr.route(self.request())
        self.assertIs(tr.error,error)

    def test_recovered_document_reaches_original_matching_and_status_rules(self):
        page=MagicMock();tr=self.transport();tr.page=page
        response=tr.opener.open.return_value
        tr.opener.open.side_effect=[TimeoutError('prior incomplete navigation'),response]
        def goto(url,**kwargs):
            if url=='about:blank':return
            route=self.request();tr.route(route)
            if route.abort.called:raise TimeoutError('Navigation aborted')
        page.goto.side_effect=goto
        page.evaluate.return_value=[{'index':0,'text':'Example Relief Inc License/Registration Number CH12345 Expiration Date 12/31/2027 Status Current'}]
        page.expect_navigation.return_value.__enter__.return_value.value=SimpleNamespace(status=200)
        with patch.object(m,'fl_verified_transport_first',return_value=True),patch.object(m.time,'sleep'),patch.object(m,'reviewed_queries_first',return_value=['Example Relief','Example Relief Inc']),patch.object(m.checker,'find_visible_input',return_value=page),patch.object(m,'readable_page_text',return_value='Example Relief Inc CH12345'),patch.object(m,'no_registry_results_seen',return_value=False),patch.object(m,'registry_candidate_fields',return_value={'status':'Current'}):
            result=m.search_fl_with_transport(page,SimpleNamespace(organization_name='Example Relief Inc',ein='123456789'),tr)
        self.assertTrue(result.success)
        self.assertEqual(result.status,'Current');self.assertEqual(result.matched_registry_identifier,'CH12345')

    def test_only_prior_error_reset_changed_in_master(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','113c86e:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        from testing.capacity_lab.parsing_scope import strip_nj_public_query
        strip_nj_public_query(new)
        expected=ast.parse('if fl_verified_transport_first() and not isinstance(self.error, FloridaCertificateError):\n    self.error = None\n').body[0]
        cls=next(n for n in new.body if getattr(n,'name','')=='FloridaVerifiedTransport')
        route=next(n for n in cls.body if getattr(n,'name','')=='route')
        matches=[n for n in route.body if ast.dump(n)==ast.dump(expected)]
        self.assertEqual(len(matches),1);route.body.remove(matches[0])
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
