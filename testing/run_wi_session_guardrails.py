"""WI transport continuity, organization isolation, and unchanged proof requirements."""
import concurrent.futures
import io
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
from run_me_wi_evidence_guardrails import EvidenceTests


class SessionTests(unittest.TestCase):
    def response(self, body, url):
        response = io.BytesIO(body.encode())
        response.status = 200
        response.geturl = lambda: url
        return response

    def test_lookup_uses_one_opener_then_releases_it(self):
        seen = []
        @c.wi_lookup_session
        def inner():
            seen.append(c.wi_request_opener())
        @c.wi_lookup_session
        def run():
            seen.append(c.wi_request_opener())
            inner()
        run(); run()
        self.assertIs(seen[0], seen[1])
        self.assertIs(seen[2], seen[3])
        self.assertIsNot(seen[0], seen[2])
        self.assertIsNone(c.WI_REQUEST_SESSION.get())

    def test_failed_lookup_does_not_poison_next_organization(self):
        @c.wi_lookup_session
        def fail():
            c.WI_REQUEST_SESSION.get()['verification_required'] = True
            raise RuntimeError('injected retrieval failure')
        with self.assertRaises(RuntimeError): fail()
        self.assertIsNone(c.WI_REQUEST_SESSION.get())
        @c.wi_lookup_session
        def recover():
            return c.WI_REQUEST_SESSION.get().get('verification_required', False)
        self.assertFalse(recover())

    def test_fifteen_concurrent_lookups_do_not_share_cookie_sessions(self):
        barrier = threading.Barrier(15)
        @c.wi_lookup_session
        def run(index):
            session = c.WI_REQUEST_SESSION.get()
            session['organization'] = index
            opener = c.wi_request_opener()
            barrier.wait(timeout=10)
            self.assertEqual(c.WI_REQUEST_SESSION.get()['organization'], index)
            return opener
        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as pool:
            openers = list(pool.map(run, range(15)))
        self.assertEqual(len({id(opener) for opener in openers}), 15)

    def test_cookie_processor_and_headers_exist_without_changing_global_opener(self):
        opener = c.wi_request_opener()
        self.assertTrue(any(isinstance(handler, c.urllib.request.HTTPCookieProcessor) for handler in opener.handlers))
        self.assertEqual(dict(opener.addheaders)['User-Agent'], c.wi_request_headers()['User-Agent'])

    def test_detail_read_uses_the_search_session(self):
        opener = Mock()
        opener.open.return_value = self.response('Name: Regional Learning Credential Number: 76543-800', c.WI_SEARCH_URL)
        @c.wi_lookup_session
        def run():
            return c.wi_http_detail_text('CredSummaryDetails.aspx?chid=765432')
        with patch.object(c.urllib.request, 'build_opener', return_value=opener), patch.object(c.urllib.request, 'urlopen') as standalone:
            self.assertIn('76543-800', run())
        opener.open.assert_called_once(); standalone.assert_not_called()

    def test_explicit_challenge_is_not_requested_repeatedly_in_same_lookup(self):
        opener = Mock()
        opener.cc_identity_diagnostics = {}
        opener.open.return_value = self.response('<title>Captcha</title>Verification required', 'https://apps.dfi.wi.gov/apps/captcha/')
        @c.wi_lookup_session
        def run():
            for _ in range(3):
                with self.assertRaises(ValueError):
                    c.wi_identity_page(opener, c.WI_SEARCH_URL, time.monotonic() + 10)
        with patch.object(c.urllib.request, 'build_opener', return_value=opener): run()
        opener.open.assert_called_once()
        self.assertTrue(opener.cc_identity_diagnostics['repeated_challenge_read_avoided'])

    def test_financial_proof_and_live_status_use_same_session_and_credential(self):
        fixture = EvidenceTests(); fixture.setUp()
        seen = []
        pages = iter([fixture.form, fixture.response, fixture.detail.replace('(Active)', '(Revoked)')])
        def read(opener, request, deadline):
            seen.append((opener, request))
            return next(pages)
        @c.wi_lookup_session
        def run():
            return c.wi_confirm_reviewed_credential(fixture.candidate, fixture.name, fixture.ein)
        with patch.object(c, 'public_profile_for_ein', return_value=fixture.profile), patch.object(c, 'wi_identity_page', side_effect=read):
            candidate = run()
        self.assertFalse(candidate['identity_conflict'])
        self.assertEqual(c.wi_status_from_detail_status(candidate['detail_status']), 'Revoked')
        self.assertEqual(len({id(opener) for opener, _ in seen}), 1)
        self.assertEqual(len(seen), 3)
        self.assertIn('Financials.aspx', seen[0][1].full_url)
        self.assertIn('CredSummaryDetails.aspx', seen[0][1].get_header('Referer'))

    def test_wrong_financial_credential_never_becomes_identity_proof(self):
        fixture = EvidenceTests(); fixture.setUp(); diagnostics = {}
        with patch.object(c, 'public_profile_for_ein', return_value=fixture.profile), patch.object(c, 'wi_identity_page', return_value=fixture.detail.replace('76543-800','99999-800')) as read:
            evidence = c.wi_foundation_filing_identity(fixture.candidate, fixture.name, fixture.ein, time.monotonic()+15, diagnostics)
        self.assertFalse(evidence)
        self.assertEqual(diagnostics['reason'], 'financial_credential_incomplete')
        read.assert_called_once()

    def test_selected_credential_recovery_uses_remaining_state_budget(self):
        # A late incomplete detail page is recoverable after the 24-second search
        # allocation, but cannot extend the existing 60-second state deadline.
        for recovered_number, expected in [('76543-800', 'Current'), ('99999-800', 'Unable to Confirm')]:
            candidate = {'registry_name':'Regional Learning Association', 'license_number':'76543-800',
                'identity_conflict':True, 'identity_detail_unavailable':True,
                'detail_href':'CredSummaryDetails.aspx?chid=765432',
                'expiration_date':c.date(2030,7,31), 'location':'CHICAGO, IL', 'score':5}
            detail = ('Name: Regional Learning Association Credential Type: Charitable Organization '
                f'Credential Number: {recovered_number} Location: CHICAGO, IL Status License is current (Active)')
            now=[0.0]
            def search(*args, **kwargs):
                now[0]=25.0
                return candidate,True
            with self.subTest(credential=recovered_number), \
                 patch.object(c.time,'perf_counter',side_effect=lambda:now[0]), \
                 patch.object(c,'wi_search_names_for_org',return_value=['Regional Learning Association']), \
                 patch.object(c,'organization_match_target_variants',return_value=['Regional Learning Association']), \
                 patch.object(c,'wi_http_search_best_match',side_effect=search), \
                 patch.object(c,'wi_http_detail_text',return_value='Loading') as direct, \
                 patch.object(c,'wi_reader_text',return_value=detail) as read, \
                 patch.object(c,'registry_address_evidence',return_value={'decision':'corroborated'}), \
                 patch.object(c,'registry_identity_preference',return_value=3):
                org=c.checker.Organization('Regional Learning Association','12-3456789')
                result=c.search_wi(None,org,max_seconds=24,progress={'deadline':60,'attempted':[],'completed':set()})
            read.assert_called_once()
            direct.assert_called_once()
            self.assertEqual(direct.call_args.kwargs['deadline'],37.0)
            self.assertEqual(read.call_args.kwargs['deadline'],37.0)
            self.assertEqual(result.status,expected)
            self.assertEqual(result.success,expected=='Current')

    def test_expired_detail_deadline_does_not_start_a_request(self):
        with patch.object(c.time,'perf_counter',return_value=50), patch.object(c.urllib.request,'urlopen') as read:
            self.assertEqual(c.wi_http_detail_text('CredSummaryDetails.aspx?chid=123',deadline=49),'')
        read.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
