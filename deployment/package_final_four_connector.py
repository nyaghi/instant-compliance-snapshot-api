"""Build a separate, origin-bound trial extension; never install over 0.5.10.

Deployment packaging only. Registry access/parsing remains in the shared
connector and identity/status interpretation remains in the master backend.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

from deployment.lab_identity import PROTECTED_ORIGINS

ROOT = Path(__file__).resolve().parents[1]
FILES = ('protocol.js','worker.js','registry-worker.js','registry-content.js','registry-ga-main.js','staging-bridge.js','recovery.js','ny-main.js','ny-content.js')
MATCHES = [
    'https://secure.nmdoj.gov/CharitySearch/*',
    'https://ago.igovsolution.net/online/Lookups/Business.aspx*',
    'https://www.sosnc.gov/online_services/search/*',
    'https://orion.nv.gov/portal/public/*',
    'https://tncab.tnsos.gov/portal/registered-charities-search*',
    'https://charitable.illinoisattorneygeneral.gov/search*',
    'https://verify.sos.ga.gov/verification/*',
]


def build(origin, destination):
    if origin in PROTECTED_ORIGINS or not re.fullmatch(r'https://[a-z0-9-]+\.onrender\.com',origin):
        raise ValueError('A separate HTTPS Render trial origin is required')
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Use a new output directory; do not overwrite an installed connector')
    destination.mkdir(parents=True)
    hashes={}
    for name in FILES:
        text=(ROOT/'browser-connector'/name).read_text(encoding='utf-8')
        if name=='protocol.js':
            assert text.count('const TRIAL_ORIGIN = "";')==1
            text=text.replace('const TRIAL_ORIGIN = "";', 'const TRIAL_ORIGIN = '+json.dumps(origin)+';')
            old='const APP_ORIGINS = Object.freeze([STAGING, "https://www.compliance-express.com", "https://compliance-express.com", ...(TRIAL_ORIGIN ? [TRIAL_ORIGIN] : [])]);'
            assert text.count(old)==1
            text=text.replace(old,'const APP_ORIGINS = Object.freeze([TRIAL_ORIGIN]);')
            text=text.replace('function registryAllowed(state, origin) {',
                              'function registryAllowed(state, origin) {\n    if (origin !== TRIAL_ORIGIN) return false;')
        # Namespace DOM messages so the installed 29.1 connector cannot also
        # react to a trial pager or page request. NY uses the mature public browser transport.
        text=text.replace('cc-ny-staging-v1','cc-final-four-trial-v1').replace('cc-ga-public-pager-v1','cc-final-four-ga-pager-v1').replace('cc-ny-page-v1','cc-final-four-ny-page-v1')
        data=text.encode('utf-8');(destination/name).write_bytes(data)
        hashes[name]=hashlib.sha256(data).hexdigest()
    manifest={
        'manifest_version':3,'name':'CharityClarity — Isolated 29.2AT Trial Connector','version':'0.6.54','minimum_chrome_version':'132',
        'description':'Public registry access for the isolated CharityClarity 29.2AT trial.',
        'permissions':['storage','browsingData','cookies'],'host_permissions':[origin+'/*',*MATCHES,'https://charities-search.ag.ny.gov/RegistrySearch*'],
        'incognito':'not_allowed','background':{'service_worker':'worker.js'},
        'content_scripts':[
            {'matches':['https://charities-search.ag.ny.gov/RegistrySearch*'],'js':['protocol.js','ny-main.js'],'run_at':'document_start','world':'MAIN'},
            {'matches':['https://charities-search.ag.ny.gov/RegistrySearch*'],'js':['ny-content.js'],'run_at':'document_start'},
            {'matches':[origin+'/*'],'js':['protocol.js','staging-bridge.js'],'run_at':'document_start'},
            {'matches':['https://verify.sos.ga.gov/verification/SearchResults.aspx*'],'js':['registry-ga-main.js'],'run_at':'document_start','world':'MAIN'},
            {'matches':MATCHES,'js':['registry-content.js'],'run_at':'document_idle'},
        ],
    }
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (destination/'build-evidence.json').write_text(json.dumps({'origin':origin,'version':'0.6.54','files':hashes,
        'installed_connector_untouched':True,'ny_uses_lab_backend':False},indent=2),encoding='utf-8')
    archive=destination.parent/(destination.name+'.zip')
    if archive.exists():raise ValueError('Refusing to overwrite an existing trial archive')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as package:
        for file in destination.iterdir():package.write(file,file.name)
    return {'directory':str(destination),'zip':str(archive),'origin':origin,'version':'0.6.54'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(build(args.origin,args.output)))
