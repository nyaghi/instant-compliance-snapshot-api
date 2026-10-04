"""Packaging-to-backend contract: prevent trial connector version skew."""
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as cc
from deployment.package_final_four_connector import build

class TrialReleaseContract(unittest.TestCase):
    def test_packaged_version_admitted_only_in_trial_for_all_mature_transports(self):
        with tempfile.TemporaryDirectory() as temp:
            package=build('https://fixture-final-four.onrender.com',Path(temp)/'connector')
            version=json.loads((Path(package['directory'])/'manifest.json').read_text())['version']
        with ExitStack() as stack:
            stack.enter_context(patch.object(cc,'ny_connector_origin_allowed',return_value=True))
            stack.enter_context(patch.object(cc,'is_verified_internal_passcode',return_value=True))
            stack.enter_context(patch.object(cc,'NY_CONNECTOR_SIGNING_KEY','test-only-signing-key-at-least-32-characters'))
            stack.enter_context(patch.object(cc,'build_search_queries',return_value=['Example Foundation']))
            stack.enter_context(patch.object(cc,'public_profile_for_ein',return_value={}))
            for state in ('NY','IL','GA'):
                for trial in (None,{'origin':'https://fixture-final-four.onrender.com'}):
                    with self.subTest(state=state,trial=bool(trial)),patch.object(cc,'trial_identity',return_value=trial):
                        status,result=cc.ny_connector_request({'email':'test@compliance-express.com','admin_passcode':'test','device_id':'test-device-1234','action':'start','state':state,'organization_name':'Example Foundation','ein':'123456789','connector_version':version},cc.NY_CONNECTOR_ORIGIN)
                        self.assertEqual(status,200 if trial else 400,result)
                        if trial:self.assertEqual(result['phase'],'search')

if __name__=='__main__':unittest.main()
