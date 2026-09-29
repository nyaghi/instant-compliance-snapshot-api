"""Explicit test executable, never imported by the runtime worker."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

job = json.load(sys.stdin)
if os.environ.get('CC_FIXTURE_DESCENDANT'):
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
    Path(os.environ['CC_FIXTURE_DESCENDANT']).write_text(str(child.pid))
time.sleep(float(os.environ.get('CC_FIXTURE_DELAY', '.05')))
result = {'ein': job['payload']['ein'], 'state': job['state'], 'app_version': job['version'],
          'success': True, 'status': 'Current', 'matched_registry_identifier': 'fixture-record',
          'matched_registry_name': job['payload']['organization_name'],
          'registration_date': '2000-01-01', 'last_filed_period': '2025-06-30',
          'identity_anchor': {'locations': ['Oakland, CA', 'Concord, CA']},
          'reviewed_names': job['payload']['alternate_names']}
out = Path(sys.argv[1]); temp = out.with_suffix('.partial')
temp.write_text(json.dumps(result)); temp.replace(out)
if os.environ.get('CC_FIXTURE_DESCENDANT'): time.sleep(120)
