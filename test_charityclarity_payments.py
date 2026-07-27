import hashlib
import hmac
import unittest

from charityclarity_payments import checkout_session_form, parse_stripe_signature, verify_stripe_signature


class PaymentHelperTests(unittest.TestCase):
    def test_checkout_form_uses_dynamic_payment_methods(self):
        form = checkout_session_form(
            price_id="price_123",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            customer_email="person@example.org",
            client_reference_id="request-1",
            metadata={"request_id": "request-1", "bad key!": "ignored-name-cleaned"},
        )
        self.assertEqual(form["mode"], "payment")
        self.assertEqual(form["line_items[0][price]"], "price_123")
        self.assertNotIn("payment_method_types[0]", form)
        self.assertTrue(form["integration_identifier"].startswith("charityclarity_ad_"))
        self.assertEqual(form["metadata[request_id]"], "request-1")
        self.assertEqual(form["metadata[badkey]"], "ignored-name-cleaned")

    def test_verify_stripe_signature(self):
        payload = b'{"type":"checkout.session.completed"}'
        secret = "whsec_test"
        timestamp = 12345
        digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
        header = f"t={timestamp},v1={digest}"
        self.assertEqual(parse_stripe_signature(header), (timestamp, [digest]))
        self.assertTrue(verify_stripe_signature(payload, header, secret, now=timestamp))
        self.assertFalse(verify_stripe_signature(payload, header, "wrong", now=timestamp))
        self.assertFalse(verify_stripe_signature(payload, header, secret, now=timestamp + 301))


if __name__ == "__main__":
    unittest.main()
