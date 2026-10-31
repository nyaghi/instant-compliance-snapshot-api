"""Package the exact validated, isolated staging connector without rewriting it.

The legacy production connector and its packager remain separate. This snapshot
is origin-bound and records the bytes actually used in staging validation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'staging_connector'
ORIGIN='https://charityclarity-final-four-29-2.onrender.com'


def verified_files(source=SOURCE):
    source=Path(source)
    expected=json.loads((ROOT/'staging_connector_hashes.json').read_text())
    files={p.name:p.read_bytes() for p in source.iterdir() if p.is_file() and p.name!='.gitattributes'}
    if set(files)!=set(expected) or len(files)!=21:
        raise ValueError('Staging connector file inventory differs from validated package')
    for name,data in files.items():
        if hashlib.sha256(data).hexdigest()!=expected[name]:
            raise ValueError('Staging connector bytes differ: '+name)
    manifest=json.loads(files['manifest.json'])
    if (manifest['version']!='0.6.135' or manifest['name']!='CharityClarity — NC Complete Profile'
            or manifest['host_permissions'][0]!=ORIGIN+'/*'
            or any('compliance-express.com' in h for h in manifest['host_permissions'])):
        raise ValueError('Staging package identity or isolation changed')
    protocol=files['protocol.js'].decode()
    if ('const TRIAL_ORIGIN = '+json.dumps(ORIGIN)+';') not in protocol or 'const APP_ORIGINS = Object.freeze([TRIAL_ORIGIN]);' not in protocol:
        raise ValueError('Isolated staging origin binding changed')
    referenced={manifest['background']['service_worker']}
    referenced.update(name for script in manifest['content_scripts'] for name in script['js'])
    for name,data in files.items():
        if name.endswith('.js'):
            for args in re.findall(r'importScripts\(([^)]*)\)',data.decode()):
                referenced.update(re.findall(r'"([a-z0-9-]+\.js)"',args))
    if not referenced<=set(files):
        raise ValueError('Packaged script dependency missing')
    return files


def build(destination,source=SOURCE):
    files=verified_files(source)
    destination=Path(destination)
    if destination.exists():
        raise ValueError('Refusing to overwrite a connector archive')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,31,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,data)
    with zipfile.ZipFile(destination) as archive:
        if set(archive.namelist())!=set(files) or any(archive.read(n)!=b for n,b in files.items()):
            raise ValueError('Archive round-trip differs')
    return {'file':str(destination),'files':len(files),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
            'build':json.loads(files['build-evidence.json'])['build'],'origin':ORIGIN}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(parser.parse_args().output)))
