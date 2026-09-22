"""Build environment-specific CC assets; preserve the rest of the Netlify site.

The deployment uploader must overlay these files on the existing deploy manifest,
never treat this directory as a complete website. Production publishing requires
an approved Chrome Web Store URL and a completed release checklist.
"""
import argparse, hashlib, json, re, shutil, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.09.20.6'
STAGE_API = 'https://instant-compliance-snapshot-api-staging-8dnk.onrender.com'
STAGE_INTERNAL = 'https://instant-compliance-snapshot-api-staging.onrender.com'
PROD_API = 'https://instant-compliance-snapshot-api-public.onrender.com'
PROD_INTERNAL = 'https://instant-compliance-snapshot-api.onrender.com'

def build(destination, environment, store_url=''):
    if store_url and not re.fullmatch(r'https://chromewebstore\.google\.com/detail/[a-z0-9-]+/[a-p]{32}', store_url):
        raise ValueError('Use the approved HTTPS Chrome Web Store listing URL.')
    destination.mkdir(parents=True, exist_ok=True)
    source = ROOT/'web-staging'
    html = (source/'index.html').read_text(encoding='utf-8')
    html = html.replace('2026.09.20.6', VERSION)
    bridge = (source/'ny-connector.js').read_text(encoding='utf-8')
    if environment == 'production':
        html = html.replace(STAGE_API, PROD_API).replace(STAGE_INTERNAL, PROD_INTERNAL)
        html = html.replace('window.location.origin === "https://staging.compliance-express.com"', '["https://www.compliance-express.com", "https://compliance-express.com"].includes(window.location.origin)')
        html = html.replace('environment: "staging"', 'environment: "production"')
        html = html.replace('&middot; Staging', '')
        html = html.replace('Confirm that staging is unlocked', 'Confirm that you are signed in')
        html = html.replace('const STAGING_ACCESS_REQUIRED = true;', 'const STAGING_ACCESS_REQUIRED = false;')
        html = html.replace('id="stagingGate" class="', 'id="stagingGate" class="hidden ')
        html = html.replace('id="appShell" class="hidden ', 'id="appShell" class="flex ')
        html = html.replace('Staging environment. Compliance Express email and passcode required.', 'For more information on CharityClarity, contact info@compliance-express.com.')
        html = html.replace(' · Staging', '').replace(' — Staging', '').replace('Staging prototype', 'New York connection')
        bridge = bridge.replace('["https://staging.compliance-express.com"]', '["https://www.compliance-express.com", "https://compliance-express.com"]')
        bridge = bridge.replace(STAGE_API, PROD_API)
        bridge = bridge.replace('three setup steps', 'Chrome Web Store installation steps').replace('three update steps', 'Chrome extension update steps')
        bridge = bridge.replace('Set up New York in 3 steps', 'Install New York connector').replace('Update New York in 3 steps', 'Update New York connector')
        paths = ['instant-compliance-snapshot.html']
    else:
        paths = ['index.html', 'instant-compliance-snapshot.html']
    for name in paths: (destination/name).write_text(html, encoding='utf-8')
    (destination/'ny-connector.js').write_text(bridge, encoding='utf-8')
    shutil.copyfile(source/'organization-identity.js', destination/'organization-identity.js')
    connector=destination/'connector';connector.mkdir(exist_ok=True)
    for name in ['privacy.html','charityclarity.png']:shutil.copyfile(source/'connector'/name,connector/name)
    if environment == 'staging':
        install=(source/'connector/index.html').read_text(encoding='utf-8').replace('0.3.6','0.4.0')
        (connector/'index.html').write_text(install,encoding='utf-8')
        validation=(source/'connector/validation.html').read_text(encoding='utf-8').replace('2026.09.20.6-staging',VERSION+'-staging')
        (connector/'validation.html').write_text(validation,encoding='utf-8')
        with zipfile.ZipFile(connector/'charityclarity-ny-staging.zip','w',zipfile.ZIP_DEFLATED) as archive:
            for item in sorted((ROOT/'browser-connector').glob('*')):
                if item.suffix in {'.js','.json','.png'}:archive.write(item,item.name)
    else:
        install_button = (f'<a class="button" href="{store_url}" target="_blank" rel="noopener">Install from Chrome Web Store</a>' if store_url
                          else '<p>The Chrome Web Store release is being finalized. Contact <a href="mailto:info@compliance-express.com">info@compliance-express.com</a> for availability.</p>')
        (connector/'index.html').write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect New York | CharityClarity</title><style>body{font:17px/1.6 system-ui;max-width:780px;margin:3rem auto;padding:0 1rem;color:#0b2a5b}img{width:260px}.button{display:inline-block;padding:.7rem 1.2rem;background:#c62828;color:white;border-radius:8px;text-decoration:none}li{margin:1.3rem 0}</style></head><body><img src="charityclarity.png" alt="CharityClarity by Compliance Express"><h1>Connect New York in three steps</h1><ol><li><strong>Install the connector.</strong> '''+install_button+'''</li><li><strong>Return to CharityClarity and refresh the page.</strong> Look for “New York connector connected.”</li><li><strong>Run your check.</strong> Keep Chrome open; the connector manages the New York registry tab and queues concurrent checks.</li></ol><p>If New York cannot complete verification, use “Refresh New York connection” in CharityClarity. The connector protects your open state pages and explains any action needed.</p><p><a href="/instant-compliance-snapshot.html">Open CharityClarity</a> · <a href="privacy.html">Connector privacy</a></p><footer>Compliance Express · <a href="https://www.compliance-express.com">www.compliance-express.com</a> · <a href="mailto:info@compliance-express.com">info@compliance-express.com</a></footer></body></html>''',encoding='utf-8')
    for name in paths+['ny-connector.js']:
        text=(destination/name).read_text(encoding='utf-8')
        targets=re.findall(r'https://instant-compliance-snapshot-api[^\s"\x27<]*\.onrender\.com',text)
        expected={STAGE_API,STAGE_INTERNAL} if environment=='staging' else {PROD_API,PROD_INTERNAL}
        assert targets and set(targets)<=expected,(name,targets)
    assert '$49' not in html and 'buy.stripe.com' not in html
    manifest={'environment':environment,'version':VERSION+('-staging' if environment=='staging' else ''),
              'store_url':store_url,'customer_installation_ready':bool(store_url),
              'overlay_files':{str(p.relative_to(destination)).replace('\\','/'):hashlib.sha1(p.read_bytes()).hexdigest() for p in destination.rglob('*') if p.is_file()}}
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);parser.add_argument('--environment',choices=['staging','production'],required=True);parser.add_argument('--store-url',default='')
    args=parser.parse_args();result=build(args.out,args.environment,args.store_url)
    args.out.with_suffix('.manifest.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
