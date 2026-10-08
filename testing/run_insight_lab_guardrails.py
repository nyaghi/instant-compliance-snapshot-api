"""Performance Lab assembly, isolation and authenticated report integration."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import registry_snapshot_server as master
from deployment import performance_lab as lab

ROOT=Path(__file__).resolve().parents[1]

class InsightLabTests(unittest.TestCase):
    def test_latest_trial_frontend_assembles_38_states_and_connected_report(self):
        with patch.object(lab,'trial_identity',return_value={'origin':'https://charityclarity-final-four-29-2.onrender.com'}),patch.object(lab,'LAB_ORIGIN','https://charityclarity-final-four-29-2.onrender.com'):
            html=lab.lab_asset('/')[0].decode()
        self.assertEqual(len(re.findall(r'name="states" value="[A-Z]{2}"',html)),38)
        self.assertIn('Connect to Insight',html)
        self.assertIn('head_start:assessment',html)
        self.assertNotIn('await window.CCHeadStart?.save()',html)
        self.assertIn('head-start-bridge.js',html)
        self.assertNotIn('instant-compliance-snapshot-api-hn4v.onrender.com',html)
        self.assertNotIn('https://staging.compliance-express.com',html)
        self.assertIn('mode="standard"',html)

    def test_protected_frontend_and_connector_templates_remain_unchanged(self):
        result=subprocess.run(['git','diff','--name-only','--','web-staging','browser-connector'],cwd=ROOT,capture_output=True,text=True,check=True)
        self.assertEqual(result.stdout.strip(),'')

    def test_head_start_assets_never_expose_json_or_escape_the_public_asset_folder(self):
        self.assertIn(b'continueAurora',lab.lab_asset('/head-start/app.js')[0])
        self.assertIn(b'head-start-logo.png',lab.lab_asset('/head-start/')[0])
        self.assertIsNone(lab.lab_asset('/head-start/../../final-four-resources.json'))
        self.assertIsNone(lab.lab_asset('/head-start/profile.json'))
        self.assertIsNone(lab.lab_asset('/head-start/../head-start-bridge.js/../../performance_lab.py'))

    def test_master_handoff_keeps_both_private_lab_and_internal_auth_boundaries(self):
        key='fixture-private-key-not-a-real-credential'
        packet=json.loads((ROOT/'testing/fixtures/connected-hospital/report-payload.json').read_text(encoding='utf-8'))
        handler=lab.build_handler(master,key,durable=object())
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(route,payload,authorization=None):
            headers={'Content-Type':'application/json'}
            if authorization:headers['Authorization']='Bearer '+authorization
            return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+route,data=json.dumps(payload).encode(),headers=headers))
        auth={'email':'connected-preview@'+master.EXEMPT_EMAIL_DOMAIN,'admin_passcode':master.ADMIN_PASSCODE}
        try:
            with tempfile.TemporaryDirectory() as directory,patch.object(master,'ARTIFACTS_DIR',Path(directory)),patch.object(lab,'trial_identity',return_value={'origin':lab.LAB_ORIGIN}),patch.object(master,'run_state_lookups_parallel',side_effect=AssertionError('Report/handoff cannot search')):
                for headers,body,expected in [(None,auth,401),(key,{},403)]:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        request('/api/head-start',{**body,'action':'save','head_start':packet['head_start']},headers)
                    self.assertEqual(error.exception.code,expected);error.exception.close()
                with request('/api/head-start',{**auth,'action':'save','head_start':packet['head_start']},key) as response:
                    self.assertEqual(json.load(response)['head_start'],packet['head_start'])
                with request('/api/report',{**auth,**packet},key) as response:
                    self.assertEqual(response.headers['Content-Type'],'application/pdf')
                    self.assertTrue(response.read().startswith(b'%PDF'))
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main(verbosity=2)
