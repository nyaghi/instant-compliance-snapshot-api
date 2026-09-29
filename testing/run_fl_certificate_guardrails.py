"""Florida transport recovery: isolation, real TLS validation, and preserved decisions."""
import http.client
import io
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.page = MagicMock()
        self.transport = c.FloridaVerifiedTransport(self.page)
        self.transport.deadline = time.monotonic() + 20
        self.transport.opener = MagicMock()
        self.route = MagicMock()
        self.route.request = SimpleNamespace(url=c.FL_CHECK_A_CHARITY_URL, method="POST",
            resource_type="document", post_data_buffer=b"name=Example+Relief&__VIEWSTATE=preserved",
            all_headers=lambda: {"Cookie": "session=kept", "Content-Type": "application/x-www-form-urlencoded",
                                 "Accept-Encoding": "gzip", "Content-Length": "1"})

    def response(self, status=200, body=b"<html>Complete results</html>", headers=None):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = status
        response.headers = Message()
        for name, value in (headers or []):
            response.headers.add_header(name, value)
        response.read1.side_effect = [body, b""]
        self.transport.opener.open.return_value = response
        return response

    def test_post_and_session_and_multiple_cookies_preserved(self):
        self.response(headers=[("Set-Cookie", "a=1; Secure"), ("Set-Cookie", "b=2; Secure")])
        self.transport.route(self.route)
        outgoing = self.transport.opener.open.call_args.args[0]
        self.assertEqual(outgoing.data, self.route.request.post_data_buffer)
        self.assertEqual(outgoing.get_header("Cookie"), "session=kept")
        self.assertEqual(outgoing.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertEqual(outgoing.get_header("Accept-encoding"), "identity")
        self.assertLessEqual(self.transport.opener.open.call_args.kwargs["timeout"], 8)
        self.assertEqual(self.route.fulfill.call_args.kwargs["headers"]["Set-Cookie"], "a=1; Secure\nb=2; Secure")

    def test_other_states_and_lookalike_hosts_never_intercepted(self):
        for url in ["https://example.gov/search", "https://csapp.fdacs.gov.attacker.test/",
                    "http://csapp.fdacs.gov/", "https://user@csapp.fdacs.gov/", "https://csapp.fdacs.gov:444/"]:
            with self.subTest(url=url):
                self.route.request.url = url
                self.transport.route(self.route)
                self.transport.opener.open.assert_not_called()
        self.assertEqual(self.route.fallback.call_count, 5)

    def test_no_network_after_deadline(self):
        self.transport.deadline = time.monotonic() - 1
        self.transport.route(self.route)
        self.transport.opener.open.assert_not_called()
        self.route.fulfill.assert_not_called()
        self.assertIsInstance(self.transport.error, TimeoutError)

    def test_deadline_checked_during_body_read(self):
        response = self.response()
        def slow_read(size):
            self.transport.deadline = 0
            return b"partial"
        response.read1.side_effect = slow_read
        self.transport.route(self.route)
        self.route.fulfill.assert_not_called()
        self.assertIsInstance(self.transport.error, TimeoutError)

    def test_partial_body_and_http_error_not_turned_into_results(self):
        response = self.response()
        response.read1.side_effect = [b"partial", http.client.IncompleteRead(b"missing")]
        self.transport.route(self.route)
        self.route.fulfill.assert_not_called()
        self.assertIsNotNone(self.transport.error)

    def test_certificate_failure_never_falls_back_to_insecure_connection(self):
        self.transport.opener.open.side_effect = urllib.error.URLError(ssl.SSLCertVerificationError("wrong host or expired"))
        self.transport.route(self.route)
        self.assertIsInstance(self.transport.error, c.FloridaCertificateError)
        self.route.fulfill.assert_not_called()
        self.route.fallback.assert_not_called()
        self.route.abort.assert_called_once_with("failed")

    def test_redirect_cannot_downgrade_or_leave_registry(self):
        for location in ["http://csapp.fdacs.gov/", "https://another.test/"]:
            self.response(status=302, headers=[("Location", location)])
            self.transport.route(self.route)
            self.route.fulfill.assert_not_called()

    def test_http_error_preserved_for_existing_parser(self):
        error = urllib.error.HTTPError(c.FL_CHECK_A_CHARITY_URL, 503, "Unavailable", Message(), io.BytesIO(b"Unavailable"))
        self.transport.opener.open.side_effect = error
        self.transport.route(self.route)
        self.assertEqual(self.route.fulfill.call_args.kwargs["status"], 503)

    def test_routes_removed_at_end_of_search_even_on_exception(self):
        def failure(page, org, transport):
            transport.enable()
            raise ValueError("test parse failure")
        with patch.object(c, "search_fl_with_transport", side_effect=failure):
            with self.assertRaises(ValueError):
                c.search_fl(self.page, SimpleNamespace())
        self.page.route.assert_called_once()
        self.page.unroute.assert_called_once_with(*self.page.route.call_args.args)

    def test_healthy_lookup_does_not_change_transport(self):
        with patch.object(c, "search_fl_with_transport", return_value="unchanged"), patch.object(c, "fl_verified_ssl_context") as ssl_factory:
            self.assertEqual(c.search_fl(self.page, SimpleNamespace()), "unchanged")
        ssl_factory.assert_not_called()
        self.page.route.assert_not_called()

    def test_public_comment_reports_certificate_error_and_avoids_repeated_retries(self):
        r = c.checker.StateResult("Example", "123456789", "FL", "Site Not Reachable", c.FL_CHECK_A_CHARITY_URL)
        r.reason_code = "FL_CERTIFICATE_ERROR"
        r.error = "Florida registry certificate verification failed"
        r.source_note = "Florida's registry security certificate could not be verified. This does not establish non-registration or delinquency."
        self.assertEqual(c.comments_for_result(r, "", c.public_status(r)), r.source_note)
        with patch.object(c, "run_state_lookup", return_value={"state": "FL", "status": "Site Not Reachable", "reason_code": r.reason_code}) as lookup:
            c.run_single_state_lookup_reliably("Example", "123456789", "FL")
        self.assertEqual(lookup.call_count, 1)

    def test_tampered_chain_member_rejected(self):
        c.fl_verified_ssl_context.cache_clear()
        original = (c.BASE_DIR / "certificates/godaddy-r1-cross-g2.pem").read_text()
        with patch.object(c.Path, "read_text", return_value=original.replace("MIIF", "MIIG", 1)):
            with self.assertRaises(c.FloridaCertificateError):
                c.fl_verified_ssl_context()
        c.fl_verified_ssl_context.cache_clear()


class OptionalDateTests(unittest.TestCase):
    def test_certificate_only_fallback_preserves_confirmed_status_and_remaining_budget(self):
        r = c.checker.StateResult("Example Foundation", "123456789", "FL", "Current", c.FL_CHECK_A_CHARITY_URL)
        r.success = True;r.matched_registry_name="Example Foundation";r.matched_registry_identifier="CH123"
        failure=RuntimeError("certificate chain failure");failure.code=60
        session=MagicMock();session.__enter__.side_effect=failure
        with patch.object(c.curl_requests,"Session",return_value=session),patch.object(c,"fl_verified_registration_issue",return_value={"identifier":"CH123"}) as recovery:
            start=time.monotonic();c.enrich_registration_date_sources(r,"Current")
        self.assertEqual(r.status,"Current");self.assertTrue(r.success)
        self.assertEqual(recovery.call_args.args[:2],("CH123","Example Foundation"))
        self.assertLessEqual(recovery.call_args.args[2]-start,12.1)
        self.assertEqual(r._cc_registration_date_evidence,{"identifier":"CH123"})
    def test_one_bounded_recovery_for_optional_network_failure(self):
        r=c.checker.StateResult("Example Foundation","123456789","FL","Current",c.FL_CHECK_A_CHARITY_URL)
        r.success=True;r.matched_registry_identifier="CH123";r.matched_registry_name="Example Foundation"
        with patch.object(c.curl_requests,"Session",side_effect=TimeoutError("network")),patch.object(c,"fl_verified_registration_issue",return_value={}) as recovery:
            c.enrich_registration_date_sources(r,"Current")
        recovery.assert_called_once();self.assertEqual(r._cc_registration_date_evidence,{})
        self.assertEqual(r.registration_date_diagnostics[0]['reason'],'TimeoutError')
        self.assertEqual(r.status,'Current');self.assertTrue(r.success)
    def test_exhausted_date_budget_cannot_start_network(self):
        with patch.object(c.urllib.request,"build_opener") as opener:
            self.assertEqual(c.fl_verified_registration_issue("CH123","Example",time.monotonic()-1),{})
        opener.return_value.open.assert_not_called()


class RealTLSValidationTests(unittest.TestCase):
    def test_valid_expired_wrong_hostname_and_untrusted_certificates(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        now = datetime.now(timezone.utc)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Temporary test CA")])
        ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2))
              .not_valid_after(now+timedelta(days=2)).add_extension(x509.BasicConstraints(ca=True,path_length=None),True)
              .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),False).sign(key, hashes.SHA256()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/"ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
            (root/"key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            for case in ["valid", "expired", "wrong_hostname", "untrusted"]:
                with self.subTest(case=case):
                    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"localhost")]))
                        .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
                        .not_valid_before(now-timedelta(days=2)).not_valid_after(now+timedelta(days=-1 if case=="expired" else 1))
                        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]),False)
                        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()),False)
                        .sign(key,hashes.SHA256()))
                    (root/"leaf.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
                    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    server.load_cert_chain(str(root/"leaf.pem"),str(root/"key.pem"))
                    listener = socket.socket();listener.bind(("127.0.0.1",0));listener.listen(1);listener.settimeout(3)
                    def serve():
                        try:
                            connection,_ = listener.accept()
                            try:
                                with server.wrap_socket(connection,server_side=True) as tls:tls.recv(1)
                            except OSError:connection.close()
                        finally:listener.close()
                    port=listener.getsockname()[1];thread=threading.Thread(target=serve);thread.start()
                    real_factory=ssl.create_default_context
                    isolated=real_factory(cafile=str(root/"ca.pem")) if case!="untrusted" else real_factory()
                    c.fl_verified_ssl_context.cache_clear()
                    with patch.object(c.ssl,"create_default_context",return_value=isolated):context=c.fl_verified_ssl_context()
                    self.assertTrue(context.check_hostname)
                    self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
                    self.assertFalse(context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN)
                    def connect():
                        with socket.create_connection(("127.0.0.1",port),timeout=3) as raw:
                            with context.wrap_socket(raw,server_hostname="wrong.example" if case=="wrong_hostname" else "localhost") as tls:tls.sendall(b"x")
                    try:
                        if case=="valid":connect()
                        else:
                            with self.assertRaises(ssl.SSLCertVerificationError):connect()
                    finally:thread.join(4);c.fl_verified_ssl_context.cache_clear()


if __name__ == "__main__":unittest.main()
