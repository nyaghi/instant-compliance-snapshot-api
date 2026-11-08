import unittest
from datetime import date
from unittest.mock import Mock, patch

import registry_snapshot_server as master


class FocusedRegistryRecovery(unittest.TestCase):
    def test_ok_footer_does_not_establish_terminal_status(self):
        text = "Status: In Existence\nOklahoma Secretary of State\nClosed on all legal holidays."
        self.assertFalse(master.ok_terminal_closed_text(master.ok_detail_record_text(text)))
        self.assertTrue(master.ok_terminal_closed_text(master.ok_detail_record_text(text.replace("In Existence", "Canceled"))))
        self.assertEqual(master.ok_filing_row_text("Open PDF\n123\tRenewal Registration"),
                         "123 Renewal Registration")

    def test_ok_document_action_bound_to_selected_row(self):
        page = Mock(url=master.OK_DETAIL_URL + "123")
        link = page.get_by_text.return_value.locator.return_value.get_by_role.return_value
        response = page.request.get.return_value
        response.ok = True
        response.url = "https://business.sos.ok.gov/CharityDocs/456.pdf"
        response.body.return_value = b"%PDF-example"
        with patch.object(master, "ok_certificate_expiration", return_value=(date(2027, 8, 18), "verified")):
            for wrong in ('https://example.org/456.pdf', '../CharityDocs/457.pdf'):
                link.get_attribute.return_value = f'window.open("{wrong}"); return false;'
                due, _ = master.ok_fetch_registration_certificate(page, "456 Renewal Registration", "Example")
                self.assertIsNone(due)
                page.request.get.assert_not_called()
            link.get_attribute.return_value = 'window.open("../CharityDocs/456.pdf"); return false;'
            due, _ = master.ok_fetch_registration_certificate(page, "456 Renewal Registration", "Example")
        self.assertEqual(due, date(2027, 8, 18))
        page.get_by_text.assert_called_with("456", exact=True)
        self.assertEqual(page.request.get.call_args.args, (response.url,))
        self.assertEqual(page.request.get.call_args.kwargs["max_redirects"], 0)

    def test_sc_reordered_broad_collision_is_distinct_from_reviewed_name(self):
        original, collision, ein = "Focus on the Family", "Family Focus", "953188150"
        self.assertTrue(master.sc_reordered_broad_name(original, collision, "Family", ein))
        self.assertFalse(master.sc_reordered_broad_name(original, collision, "Family Focus", ein))
        self.assertFalse(master.sc_reordered_broad_name(original, "Focus Family", "Family", ein))
        with patch.object(master, "known_names_for_ein", return_value=[collision]):
            self.assertFalse(master.sc_reordered_broad_name(original, collision, "Family", ein))
