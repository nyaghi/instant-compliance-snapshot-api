"""An explicit Wisconsin challenge must not become missing identity evidence."""
import io,sys,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class VerificationTests(unittest.TestCase):
    def test_verification_redirect_stops_without_retry(self):
        response=io.BytesIO(b'<html><title>Captcha</title>Verification required</html>')
        response.status=200;response.geturl=lambda:'https://apps.dfi.wi.gov/apps/captcha/'
        opener=Mock();opener.open.return_value=response;opener.cc_identity_diagnostics={}
        with patch.object(c.time,'sleep') as sleep,self.assertRaises(ValueError):
            c.wi_identity_read(lambda:c.wi_identity_page(opener,'https://apps.dfi.wi.gov/ice/berg/Registration/Financials.aspx?chid=123',time.monotonic()+20),time.monotonic()+20,'Wisconsin financial page',opener.cc_identity_diagnostics)
        opener.open.assert_called_once();sleep.assert_not_called()
        self.assertTrue(opener.cc_identity_diagnostics['verification_required'])
        self.assertEqual(opener.cc_identity_diagnostics['incomplete_pages'][0]['title'],'Captcha')

    def lookup(self,candidate):
        org=c.checker.Organization('Regional Learning Association Foundation','12-3456789')
        with patch.object(c,'wi_search_names_for_org',return_value=[org.organization_name]),patch.object(c,'organization_match_target_variants',return_value=[org.organization_name]),patch.object(c,'wi_http_search_best_match',return_value=(candidate,True)),patch.object(c,'wi_confirm_cross_state_credential',return_value=candidate),patch.object(c,'wi_reader_search_best_match') as reader:
            result=c.search_wi(None,org)
        reader.assert_not_called()
        return result

    def test_foundation_and_address_challenges_explain_access_failure(self):
        for foundation in [False,True]:
            candidate={'identity_conflict':True,'registry_name':'Regional Learning Association','license_number':'12345-800'}
            diagnostic={'verification_required':True,'incomplete_pages':[{'title':'Captcha'}]}
            if foundation:candidate.update(identity_review_evidence={'reason':'Foundation omitted'},financial_identity_diagnostics=diagnostic)
            else:candidate['address_evidence']={'decision':'conflict','financial_corroboration':diagnostic}
            with self.subTest(foundation=foundation):
                result=self.lookup(candidate)
                self.assertFalse(result.success);self.assertEqual(result.status,'Unable to Confirm')
                self.assertEqual(result.reason_code,'WI_IDENTITY_VERIFICATION_REQUIRED')
                self.assertFalse(result.matched_registry_identifier)
                self.assertIn('human-verification',c.comments_for_result(result,'',c.public_status(result)))
                with patch.object(c,'run_state_lookup',return_value={'state':'WI','status':result.status,'reason_code':result.reason_code}) as lookup,patch.object(c.time,'sleep') as sleep:
                    row=c.run_single_state_lookup_reliably('Regional Learning Foundation','123456789','WI')
                lookup.assert_called_once();sleep.assert_not_called()
                self.assertFalse(c.fragile_batch_result_needs_confirmation(row))

    def test_completed_identity_disagreement_remains_review(self):
        result=self.lookup({'identity_conflict':True,'registry_name':'Regional Learning Association','license_number':'12345-800','identity_review_evidence':{'reason':'Foundation omitted'},'financial_identity_diagnostics':{'reason':'financial_values_not_corroborated'}})
        self.assertEqual(result.status,'Needs Review');self.assertEqual(result.reason_code,'WI_FOUNDATION_IDENTITY_REVIEW')
        comment=c.comments_for_result(result,'',c.public_status(result))
        for evidence in ['Regional Learning Association','12345-800','does not show an EIN',
                         'organization addresses','identity remains unconfirmed','not because no record was found',
                         'Confirm with Wisconsin']:
            self.assertIn(evidence,comment)
        self.assertNotIn('financial',comment.lower())

    def test_generic_incomplete_page_is_not_misclassified_as_verification(self):
        for url in ['https://apps.dfi.wi.gov/ice/berg/Registration/Financials.aspx','https://example.test/apps/captcha/']:
            response=io.BytesIO(b'<html>Incomplete response</html>');response.geturl=lambda:url;response.status=200
            opener=Mock();opener.open.return_value=response;opener.cc_identity_diagnostics={}
            self.assertIn('Incomplete',c.wi_identity_page(opener,url,time.monotonic()+20))
            self.assertNotIn('verification_required',opener.cc_identity_diagnostics)

if __name__=='__main__':unittest.main(verbosity=2)
