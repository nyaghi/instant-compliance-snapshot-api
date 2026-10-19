"""Original visuals only: local browser fixture and unchanged state PDF page."""
from pathlib import Path
import io,json,sys,time,html
ROOT=Path(__file__).resolve().parents[1];HERE=ROOT.parent;PROJECT=HERE.parent.parent
sys.path.insert(0,str(ROOT))
import registry_snapshot_server as c
from deployment import state_snapshots as s
from pypdf import PdfReader
OUT=PROJECT/'output/pdf';OUT.mkdir(parents=True,exist_ok=True)
def save(asset,name):
    meta,raw=s.validate_asset(asset,ein=asset['ein'],state=asset['state'],run_id=asset['run_id'])
    pdf=s.render_pdf(meta,raw);(OUT/name).write_bytes(pdf)
    return {'file':str(OUT/name),'pages':len(PdfReader(io.BytesIO(pdf)).pages),'kind':meta['kind']}
previews=[]
with c.checker.sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    try:
        page=browser.new_page(viewport={'width':1000,'height':900})
        page.set_content('''<html><body style="font:20px Arial;padding:30px"><h1>LOCAL TEST FIXTURE</h1>
        <p>This is a local screenshot test, not an actual organization or state finding.</p>
        <h2>Example Nonprofit Fixture</h2><p>EIN: 00-0000000</p><p>Record ID: TEST-111</p>
        <p>Status: fixture only</p><p style="margin-top:900px">End of full-page capture</p></body></html>''')
        raw=page.screenshot(type='png',full_page=True)
        asset=s.asset_for(raw,kind='image',state='OR',ein='000000000',run_id='local-fixture-0000000001',
            source_url='https://justice.oregon.gov/Charities/',organization_name='Example Nonprofit Fixture - LOCAL TEST',
            identifier='TEST-111',record_name='Example Nonprofit Fixture',
            capture_note='LOCAL TEST FIXTURE. No registry was queried. This demonstrates the PDF layout only; the screenshot contains fictional test data.')
        previews.append(save(asset,'state-snapshot-actual-pixels-local-fixture.pdf'))
        page.close()
        ui=browser.new_page(viewport={'width':1100,'height':1000})
        ui.set_content('''<html><style>body{font:16px Arial;padding:35px;color:#24364b}td{border:1px solid #d5dce5;padding:22px;vertical-align:top}table{border-collapse:collapse;width:100%}a{color:#164d8c;display:block;margin:14px 0}button{margin:12px 6px 0 0;padding:8px}p{margin:10px 0}</style>
        <body><h1>LOCAL INTERFACE PREVIEW</h1><p>Saved PDF links appear immediately beneath the comment and within each identity choice.</p>
        <table><tr><td>Oregon</td><td>Upcoming Filing</td><td id="comment">The confirmed completed report determines the next filing cycle.</td></tr></table></body></html>''')
        ui.add_script_tag(path=str(ROOT/'web-staging/identity-review.js'))
        ui.evaluate('''() => {const el=document.querySelector('#comment'); const result={state:'OR',status:'Upcoming Filing',evidence_url:'/state-snapshots/'+'a'.repeat(64)+'.pdf',identity_review:{exclusive:true,candidates:[{id:'1',name:'Example Nonprofit Fixture',identifier:'TEST-111',location:'Test address',raw_status:'Fixture only',evidence_url:'/state-snapshots/'+'b'.repeat(64)+'.pdf'}]}};CCIdentityReview.renderEvidence(el,result);CCIdentityReview.render(el,result,async()=>{},async()=>{});}''')
        ui.screenshot(path=str(HERE/'snapshot-interface-preview.png'),full_page=True);ui.close()
    finally:browser.close()
org=next(o for o in json.loads((ROOT/'testing/fixtures/oct19-cohort.json').read_text()) if o['name']=='Partnership for Civil Justice Fund')
with s.CaptureRun(org['name'],org['ein'],'NH') as run:
    r={'ein':org['ein'],'state':'NH','matched_registry_name':org['name'],'matched_registry_identifier':'12835','source_url':'https://mm.nh.gov/files/uploads/doj/remote-docs/registered-charities.pdf'}
    s.downloaded_record(c,r);captured=run.finish(r)
    assets=captured.get('_worker_source_archives',[])
    assert assets and assets[0]['kind']=='source_pdf',[(d[2],len(d[1])) for d in run.documents]
    previews.append(save(assets[0],'state-snapshot-original-nh-page.pdf'))
(HERE/'snapshot-original-visual-previews.json').write_text(json.dumps(previews,indent=2))
print(json.dumps(previews,indent=2))
