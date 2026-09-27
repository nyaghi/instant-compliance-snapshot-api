"""Optional Florida dates: bounded recovery, complete responses, same credential."""
import io
import ast
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

FORM='<input type="hidden" name="__VIEWSTATE" value="fixture">'
DETAIL=('<table id="cpMainContent_MasterGv_dataTab_0"><tr><td><strong>Example Foundation</strong></td></tr></table>'
        '<p>License Type License# Issued Expires Status Charitable Organization CH123 06/10/93 10/22/26 Registered </p>')


class Dates(unittest.TestCase):
    def result(self):
        r=c.checker.StateResult('Example Foundation','123456789','FL','Current',c.FL_CHECK_A_CHARITY_URL)
        r.success=True;r.matched_registry_identifier='CH123';r.matched_registry_name='Example Foundation'
        return r

    def curl(self,source):
        response=MagicMock(status_code=200,text=source)
        response.raise_for_status.return_value=None
        return response

    def test_healthy_date_needs_no_recovery_and_retains_label(self):
        r=self.result();session=MagicMock();session.__enter__.return_value=session
        session.get.return_value=self.curl(FORM);session.post.return_value=self.curl(DETAIL)
        with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'fl_verified_registration_issue') as retry:
            c.enrich_registration_date_sources(r,'Current')
        retry.assert_not_called()
        self.assertEqual(c.registration_date_metadata(r)['registration_date'],'1993-06-10')
        self.assertEqual(r.registration_date_diagnostics[-1]['reason'],'CONFIRMED')
        self.assertEqual(session.post.call_args.kwargs['data']['ctl00$cpMainContent$LicenseTb'],'CH123')

    def test_slow_valid_credential_can_finish_without_restarting_the_form(self):
        # Reproduce a 4-second public response: the old 3-second allowance
        # discards it and needs another form; the new allowance keeps its evidence.
        source=subprocess.check_output(['git','show','88e5f17:registry_snapshot_server.py'],cwd=Path(c.__file__).parent).decode()
        old=next(n for n in ast.parse(source).body if getattr(n,'name','')=='enrich_registration_date_sources')
        namespace=dict(c.__dict__)
        namespace['fl_verified_registration_issue']=lambda *args: {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[old],type_ignores=[])),'old FL date reader','exec'),namespace)
        for reader,expected in ((namespace['enrich_registration_date_sources'],''),(c.enrich_registration_date_sources,'1993-06-10')):
            r=self.result();clock=[0.0];session=MagicMock();session.__enter__.return_value=session
            session.get.return_value=self.curl(FORM)
            def slow_post(*args,**kwargs):
                limit=kwargs['timeout'];clock[0]+=min(limit,4.0)
                if limit<4:raise TimeoutError('slow credential response')
                return self.curl(DETAIL)
            session.post.side_effect=slow_post
            with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'fl_verified_registration_issue',return_value={}):
                reader(r,'Current')
            self.assertEqual(c.registration_date_metadata(r)['registration_date'],expected)
            self.assertEqual(r.status,'Current')

    def test_longer_post_does_not_extend_total_date_deadline_or_accept_late_bytes(self):
        clock=[0.0];r=self.result();session=MagicMock();session.__enter__.return_value=session
        session.get.return_value=self.curl(FORM)
        def late_post(*args,**kwargs):
            self.assertLessEqual(kwargs['timeout'],6.0)
            clock[0]=12.1
            return self.curl(DETAIL)
        session.post.side_effect=late_post
        with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'fl_verified_registration_issue') as recovery:
            c.enrich_registration_date_sources(r,'Current')
        recovery.assert_not_called()
        self.assertEqual(c.registration_date_metadata(r)['registration_date'],'')
        self.assertEqual(r.status,'Current')

    def test_slow_form_and_credential_fit_same_total_allowance(self):
        # Both failed cloud controls timed out on the form, before a credential
        # request. A four-second form and four-second credential fit inside 12s.
        r=self.result();clock=[0.0];session=MagicMock();session.__enter__.return_value=session
        def slow(source, *args, **kwargs):
            limit=kwargs['timeout'];clock[0]+=min(limit,4.0)
            if limit<4:raise TimeoutError('slow form/credential')
            return self.curl(source)
        session.get.side_effect=lambda *a,**kw:slow(FORM,*a,**kw)
        session.post.side_effect=lambda *a,**kw:slow(DETAIL,*a,**kw)
        with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'fl_verified_registration_issue') as retry:
            c.enrich_registration_date_sources(r,'Current')
        retry.assert_not_called()
        self.assertEqual(c.registration_date_metadata(r)['registration_date'],'1993-06-10')
        self.assertEqual(clock[0],8.0)

    def test_late_form_does_not_start_credential_or_recovery(self):
        r=self.result();clock=[0.0];session=MagicMock();session.__enter__.return_value=session
        def late_form(*args,**kwargs):
            clock[0]=12.1
            return self.curl(FORM)
        session.get.side_effect=late_form
        with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c,'fl_verified_registration_issue') as retry:
            c.enrich_registration_date_sources(r,'Current')
        session.post.assert_not_called();retry.assert_not_called()
        self.assertEqual(c.registration_date_metadata(r)['registration_date'],'')

    def test_only_request_allowances_change_in_date_reader(self):
        source=subprocess.check_output(['git','show','88e5f17:registry_snapshot_server.py'],cwd=Path(c.__file__).parent).decode()
        before=next(n for n in ast.parse(source).body if getattr(n,'name','')=='enrich_registration_date_sources')
        from testing.capacity_lab.parsing_scope import strip_fl_business_lookup
        current=ast.parse(Path(c.__file__).read_text(encoding='utf-8'))
        strip_fl_business_lookup(current)
        after=next(n for n in current.body if getattr(n,'name','')=='enrich_registration_date_sources')
        requests=[n for n in ast.walk(after) if isinstance(n,ast.Call) and ast.unparse(n.func) in {'session.get','session.post'}]
        self.assertEqual(len(requests),2)
        for request in requests:
            timeout=next(k.value for k in request.keywords if k.arg=='timeout')
            expected='min(6.0, max(0.001, date_deadline - time.monotonic()))' if ast.unparse(request.func)=='session.get' else 'min(6.0, date_deadline - time.monotonic())'
            self.assertEqual(ast.unparse(timeout),expected)
            timeout.args[0].value=3.0
        self.assertEqual(ast.dump(before),ast.dump(after))

    def test_wrong_credential_never_accepted_or_retried_as_transport(self):
        for text in (DETAIL.replace('CH123','CH999'),DETAIL.replace('Example Foundation','Local Chapter')):
            r=self.result();session=MagicMock();session.__enter__.return_value=session
            session.get.return_value=self.curl(FORM);session.post.return_value=self.curl(text)
            with patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'fl_verified_registration_issue') as retry:
                c.enrich_registration_date_sources(r,'Current')
            retry.assert_not_called()
            self.assertEqual(c.registration_date_metadata(r)['registration_date'],'')
            self.assertEqual(r.registration_date_diagnostics[-1]['reason'],'DATE_EVIDENCE_UNCONFIRMED')
            self.assertEqual(r.status,'Current')

    def test_missing_form_is_diagnosed_not_interpreted_as_absent_date(self):
        r=self.result();session=MagicMock();session.__enter__.return_value=session
        session.get.return_value=self.curl('<p>Temporarily unavailable</p>')
        with patch.object(c.curl_requests,'Session',return_value=session):c.enrich_registration_date_sources(r,'Current')
        session.post.assert_not_called()
        self.assertEqual(r.registration_date_diagnostics[-1]['reason'],'FORM_INCOMPLETE')

    def verified(self,bodies,headers=None):
        opener=MagicMock()
        responses=[]
        for body in bodies:
            response=MagicMock();response.__enter__.return_value=response
            stream=io.BytesIO(body.encode());response.read1.side_effect=stream.read1
            response.headers=headers or {'Content-Length':str(len(body.encode()))}
            responses.append(response)
        opener.open.side_effect=responses
        return opener

    def test_verified_recovery_reads_complete_same_credential(self):
        opener=self.verified([FORM,DETAIL]);notes=[]
        with patch.object(c.urllib.request,'build_opener',return_value=opener):
            evidence=c.fl_verified_registration_issue('CH123','Example Foundation',time.monotonic()+10,notes)
        self.assertEqual(evidence['identifier'],'CH123')
        self.assertEqual(notes[-1]['reason'],'CONFIRMED')
        self.assertLessEqual(opener.open.call_args.kwargs['timeout'],4)

    def test_truncated_response_rejected_and_failure_visible(self):
        opener=self.verified([FORM],{'Content-Length':'999999'});notes=[]
        with patch.object(c.urllib.request,'build_opener',return_value=opener):
            self.assertEqual(c.fl_verified_registration_issue('CH123','Example Foundation',time.monotonic()+10,notes),{})
        self.assertEqual(notes[-1]['reason'],'ValueError')
        self.assertEqual(opener.open.call_count,1)

    def test_deadline_never_accepts_late_credential(self):
        opener=self.verified([FORM,DETAIL]);notes=[]
        ticks=iter([0,0,0,0,0,0,0,0,20])
        with patch.object(c.urllib.request,'build_opener',return_value=opener),patch.object(c.time,'monotonic',side_effect=lambda:next(ticks,20)):
            self.assertEqual(c.fl_verified_registration_issue('CH123','Example Foundation',10,notes),{})
        self.assertNotEqual(notes[-1]['reason'],'CONFIRMED')

    def test_other_states_and_unconfirmed_results_do_not_read_dates(self):
        for state,status in [('CO','Current'),('FL','Unable to Confirm')]:
            r=self.result();r.state=state;r.status=status
            with patch.object(c.curl_requests,'Session') as network:c.enrich_registration_date_sources(r,status)
            network.assert_not_called()

    def test_no_budget_does_not_start_optional_network(self):
        with patch.object(c,'registration_date_budget_available',return_value=False),patch.object(c.curl_requests,'Session') as network:
            c.enrich_registration_date_sources(self.result(),'Current',time.perf_counter())
        network.assert_not_called()


if __name__=='__main__':unittest.main(verbosity=2)
