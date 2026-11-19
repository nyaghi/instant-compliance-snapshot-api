"""Local browser test of actual UI + service. Every request is intercepted to
an isolated in-memory HTTP test service; no live staging/IRS/state traffic.
"""
import base64,io,json,os,threading,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright,expect
from deployment import tn_extensions_demo as t,tn_extension_refresh as refresh
from types import SimpleNamespace
from testing.test_tn_extensions_demo import Accounts,ACCOUNT,NOW

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('CC_TN_TEST_OUTPUT',str(ROOT/'testing/tn-workflow-evidence')));OUT.mkdir(parents=True,exist_ok=True)
ORIGIN='https://charityclarity-final-four-29-2.onrender.com'
TEST_MASTER=SimpleNamespace(NY_CONNECTOR_SIGNING_KEY='local-only-test-source-key-12345678901234567890',APP_VERSION='local-test')
TEST_COOKIE=SimpleNamespace(headers={'Cookie':'__Host-cc_alerts='+'a'*43})
ORG={'fcc':('680412350','Foundation for California Community Colleges'),'fca':('440610626','Fellowship of Christian Athletes'),'boston':('042774441',"Children's Hospital Corporation"),'global':('521273585','Global Impact'),'closed':('521125072','Society for Scholarly Publishing')}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,body,kind='application/json',status=200):
        if not isinstance(body,bytes):body=json.dumps(body).encode()
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def setup_service(self):
        if not hasattr(self.server,'accounts'):
            self.server.accounts=Accounts();del self.server.accounts.extension_reference_provider
            self.server.offset=0;self.server.calls=[]
        return t.Service(self.server.accounts,source_key=TEST_MASTER.NY_CONNECTOR_SIGNING_KEY,session_binding=refresh.session_binding(TEST_COOKIE),source_version=TEST_MASTER.APP_VERSION),self.server.accounts.c
    def do_GET(self):
        service,c=self.setup_service();path=urlsplit(self.path).path
        if path.startswith(t.PREFIX+'/documents/'):
            row=c.execute('SELECT body FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s',(path.rsplit('/',1)[-1],ACCOUNT)).fetchone()
            return self.send(bytes(row['body']),'application/pdf') if row else self.send({},status=404)
        if path in ['/tn-extensions-demo.js','/tn-extensions-demo.css','/tn-extension-portal-rehearsal.js']:
            return self.send((ROOT/'web-staging'/path[1:]).read_bytes(),'text/javascript' if path.endswith('.js') else 'text/css')
        if path=='/__advance':self.server.offset=17;return self.send({'offset':17})
        if path=='/__second':self.server.second=True;return self.send({'synthetic_second_fixture':True})
        if path=='/__old_capture':
            row=c.execute('SELECT data FROM cc_tn_extension_demo_requests WHERE account=%s AND ein=%s',(ACCOUNT,'042774441')).fetchone()
            r=row['data'];r['confirmation_capture']['format_version']=1;service.save(c,ACCOUNT,r,NOW+self.server.offset);c.db.commit();return self.send({'test_only_old_capture':True})
        if path=='/__state':
            rows=c.execute('SELECT data FROM cc_tn_extension_demo_requests WHERE account=%s',(ACCOUNT,)).fetchall()
            return self.send({'requests':[r['data'] for r in rows],'calls':self.server.calls,'document_count':c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n']})
        key=parse_qs(urlsplit(self.path).query).get('case',['fcc'])[0];identifier,name=ORG[key]
        reference=t.public_facts(identifier)
        result=dict(state='TN',ein=identifier,organization_name=name,matched_registry_name=reference['name'],matched_registry_identifier=reference['coid'],raw_status_text='Active' if reference['current_verified'] else 'Expired',computed_due_date=reference['expiration'],renewal_filing_type='filed_period_end',renewal_filing_value='2025-'+reference['period_end'][5:] if reference.get('period_end') else '2025-06-30',source_url=t.SOURCE,success=True,status='Upcoming Filing')
        result['extension_source_token']=refresh.issue_public_proof(TEST_MASTER,TEST_COOKIE,result,NOW+self.server.offset)
        assert result['extension_source_token']
        html='''<!doctype html><html><head><meta charset="utf-8"><title>Local isolated Tennessee workflow test</title><style>*,::before,::after{box-sizing:border-box}p,h1,h2,h3{margin:0}h1,h2,h3{font-weight:inherit;font-size:inherit}</style><link rel="stylesheet" href="/tn-extensions-demo.css"></head><body style="font:16px Arial;margin:24px"><h1>CharityClarity local test — Demo only</h1><p id="mainReady">Main results ready</p><section id="resultPanel"><table><tbody id="resultRows"><tr><td>Tennessee</td><td>Upcoming Filing</td><td></td></tr></tbody></table></section><script src="/tn-extension-portal-rehearsal.js"></script><script src="/tn-extensions-demo.js"></script><script>CCTennesseeExtensions.render(REPLACE_RESULT)</script></body></html>'''
        # Explicit local-only transport fixtures. Production endpoints never
        # accept caller-supplied public results or account credentials here.
        fixture='''<script>
        window.CCIdentityConfig=()=>({email:'offline@example.org',admin_passcode:'TEST',device_id:'test-device'});
        window.CCNYConnector={lookup:async input=>{const r=await fetch('/__public',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ein:input.ein,nonce:input.extensionRefresh})});if(!r.ok)throw new Error('Test public source unavailable');return r.json();}};
        window.addEventListener('message',event=>{const m=event.data;if(m?.channel==='cc-tn-extension-account-v1'&&m.direction==='request')window.postMessage({channel:m.channel,direction:'response',id:m.id,nonce:m.nonce,extension_id:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',observation:{state:'checked',records:m.coid==='CO901'?[{tracking:'9000001234',coid:m.coid,description:'First Extension Request for GLOBAL IMPACT',type:'Extension Request',status:'Rejected',updated:'Test timestamp',source:'https://tncab.tnsos.gov/portal/my-filings',identity_method:'co_number'}]:[]}},location.origin);});
        </script>'''
        html=html.replace('<script>CCTennesseeExtensions.render',fixture+'<script>CCTennesseeExtensions.render')
        return self.send(html.replace('REPLACE_RESULT',json.dumps([result])).encode(),'text/html')
    def do_POST(self):
        service,c=self.setup_service()
        p=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if urlsplit(self.path).path=='/__public':
            from deployment import tn_extension_refresh as refresh
            reference=t.public_facts(p['ein'])
            public=dict(state='TN',ein=p['ein'],organization_name=reference['name'],matched_registry_name=reference['name'],matched_registry_identifier=reference['coid'],raw_status_text='Active' if reference['current_verified'] else 'Expired',computed_due_date=reference['expiration'],renewal_filing_type='filed_period_end',renewal_filing_value='2025-'+reference['period_end'][5:] if reference.get('period_end') else '2025-06-30',source_url=t.SOURCE,success=True,status='Upcoming Filing')
            with c.db:refresh.complete(service,c,ACCOUNT,p['ein'],p['nonce'],public,NOW+self.server.offset)
            return self.send(public)
        self.server.calls.append({'action':p.get('action'),'ein':p.get('ein'),'id':p.get('id')})
        try:
            with c.db:
                if p.get('action')=='prepare' and getattr(self.server,'second',False):
                    result=service.create(c,ACCOUNT,dict(ein=p['ein'],name='Synthetic second-extension example',scenario='second-open'),NOW+self.server.offset)
                else:result=service.dispatch(c,ACCOUNT,p,NOW+self.server.offset)
                if p.get('action') in {'check','status'} and getattr(self.server,'second',False):
                    facts=t.demo_facts(p['ein'],'Synthetic second-extension example','second-open')
                    facts['account_check']=result['facts'].get('account_check',{})
                    facts['existing_filing']=True if any(x['scenario']=='second-open' and x['status'] in {'Extension submitted','Receipt acknowledged','Submission unconfirmed'} for x in result['requests']) else None
                    result.update(facts=facts,eligibility=t.eligibility(facts,t.day(t.AS_OF)),eligibility_explanation=t.eligibility_explanation(facts,t.day(t.AS_OF)),needs_prior_confirmation=facts['existing_filing'] is None)
            self.send(result)
        except t.Invalid as e:self.send({'error':str(e)},status=400)

def main():
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port);network=[]
    def get(path):return urllib.request.urlopen(base+path).read()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True);context=browser.new_context(viewport={'width':1280,'height':1000});drop_submit={'once':False}
            def route(request_route):
                request=request_route.request;parsed=urlsplit(request.url)
                assert parsed.netloc==urlsplit(ORIGIN).netloc,'No external test traffic allowed'
                network.append(parsed.path)
                req=urllib.request.Request(base+parsed.path+('?' +parsed.query if parsed.query else ''),data=request.post_data_buffer,method=request.method,headers={'Content-Type':request.headers.get('content-type','application/json')})
                try:
                    with urllib.request.urlopen(req) as response:
                        raw=response.read()
                        if request.post_data and json.loads(request.post_data).get('action')=='submit' and drop_submit['once']:
                            drop_submit['once']=False;request_route.abort('failed');return
                        request_route.fulfill(status=response.status,body=raw,headers={'content-type':response.headers['Content-Type']})
                except urllib.error.HTTPError as response:request_route.fulfill(status=response.code,body=response.read(),headers={'content-type':'application/json'})
            context.route('**/*',route);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            def go(key):
                page.goto(ORIGIN+'/?case='+key);page.get_by_text('Main results ready',exact=True).wait_for()
                page.locator('#tnFileExtension').wait_for()
                assert page.get_by_role('link',name='View captured confirmation screen — Demo only').count()==0,'No saved filing link before explicit check'
                page.locator('#tnCheckExtensions').click();expect(page.locator('#tnCheckExtensions')).to_be_enabled(timeout=15000);page.locator('#tnFileExtension').wait_for()
            def prepare():
                page.locator('#tnFileExtension').click();page.locator('#tnInitialPrior').select_option('no')
                if page.locator('#tnOtherPeriod').count():
                    assert page.locator('#tnPrepareExtension').is_disabled()
                    page.locator('#tnOtherPeriod').check()
                page.locator('#tnPrepareExtension').click();page.locator('#tnSubmitDemo').wait_for()
            go('fcc');assert 'Eligibility findings:' in page.locator('.tn-extension-row').inner_text()
            assert 'registration is Active' in page.locator('.tn-extension-row').inner_text()
            prepare();page.get_by_text('CO number and matching test attachment added automatically.',exact=False).wait_for()
            assert page.locator('#tnPortalUpload').evaluate('el=>el.files[0].name')=='Reason statement - Demo only.pdf'
            assert page.locator('#tnIRSAnswer').count()==0;assert page.locator('#tnSubmitIRS').count()==0;assert page.locator('#tnSupportUpload').count()==0
            assert 'Federal Form 8868 deadline' not in page.locator('#tnExtensionDialog').inner_text()
            page.locator('#tnFirstReason').fill('Additional time is needed to complete the audited financial statements.')
            assert page.locator('#tnSubmitDemo').is_disabled()
            page.locator('#tnPrepareFirst').click();page.get_by_text('CO number and matching test attachment added automatically.',exact=False).wait_for()
            page.locator('#tnReviewed').check();page.locator('#tnAuthorized').check();page.get_by_text('Test response options',exact=True).click();page.locator('#tnTestResponse').select_option('returned');page.locator('#tnSubmitDemo').click()
            page.get_by_text('Receipt acknowledged — Demo only',exact=True).wait_for(timeout=12000)
            assert 'State review: Returned for correction' in page.locator('#tnExtensionDialog').inner_text()
            page.screenshot(path=str(OUT/'FCC-FIRST-EXTENSION-NO-FEDERAL-STEP.png'),full_page=True)
            page.locator('#tnClose').click()
            go('closed');assert page.locator('#tnFileExtension').is_disabled()
            go('fca');prepare();page.locator('#tnFirstSupport').select_option('irs')
            assert page.locator('#tnSubmitDemo').is_disabled();assert page.locator('#tnSubmitIRS').count()==0
            page.get_by_text('Demo documents',exact=True).click();page.locator('#tnUseDemoEvidence').click()
            page.get_by_text('CO number and matching test attachment added automatically.',exact=False).wait_for()
            page.locator('#tnReviewed').check();page.locator('#tnAuthorized').check();page.locator('#tnSubmitDemo').click()
            page.get_by_text('Receipt acknowledged — Demo only',exact=True).wait_for(timeout=12000);page.locator('#tnClose').click()
            get('/__second');go('boston');prepare();page.locator('#tnIRSAnswer').select_option('no')
            for key,value in dict(books='Demo Books Custodian',phone='202-555-0100',tax_a='0',tax_b='0',tax_c='0').items():page.locator('#irs_'+key).fill(value)
            page.locator('#tnIRSReviewed').check();page.locator('#tnSubmitIRS').click();page.get_by_text('CO number and matching test attachment added automatically.',exact=False).wait_for()
            assert page.locator('#tnPortalCO').input_value()=='CO52803'
            assert page.locator('#tnPortalUpload').evaluate('(e)=>e.files.length')==1
            page.locator('#tnReviewed').check();page.locator('#tnAuthorized').check();page.get_by_text('Test response options',exact=True).click();page.locator('#tnTestResponse').select_option('delayed');page.locator('#tnSubmitDemo').click()
            page.locator('#tnConfirmationCard').wait_for();page.get_by_text('Confirmation screen captured and saved with this application.',exact=True).wait_for(timeout=12000)
            page.screenshot(path=str(OUT/'TEST-SUBMISSION-CONFIRMATION.png'),full_page=True)
            get('/__advance')
            page.get_by_text('Receipt acknowledged — Demo only',exact=True).wait_for(timeout=12000)
            assert 'Isolated Tennessee test service' in page.locator('#tnExtensionDialog').inner_text()
            state=json.loads(get('/__state'));boston=next(x for x in state['requests'] if x['ein']=='042774441')
            assert boston['state_sends']==1 and boston['irs_submission']['sends']==1
            for key in ['irs_filed','irs_acceptance','application','acknowledgment','confirmation_screen']:
                assert key in boston['documents'];(OUT/(key+'.pdf')).write_bytes(get(boston['documents'][key]))
            original=dict(boston['documents']);original_count=state['document_count'];page.locator('#tnClose').click();go('boston')
            page.get_by_role('link',name='View captured confirmation screen — Demo only').wait_for()
            assert page.locator('#tnFileExtension').is_disabled();assert page.get_by_role('link',name='View captured confirmation screen — Demo only').count()==1
            refreshed=json.loads(get('/__state'));later=next(x for x in refreshed['requests'] if x['id']==boston['id']);assert later['documents']==original;assert refreshed['document_count']==original_count
            get('/__old_capture');page.goto(ORIGIN+'/?case=boston');page.locator('#tnFileExtension').wait_for();page.locator('#tnCheckExtensions').click();page.get_by_role('button',name='View submitted filing',exact=True).click()
            capture_link=page.locator('#tnExtensionDialog').get_by_role('link',name='View captured confirmation screen — Demo only',exact=True)
            expect(capture_link).not_to_have_attribute('href',original['confirmation_screen'],timeout=12000)
            migrated=json.loads(get('/__state'));latest=next(x for x in migrated['requests'] if x['id']==boston['id'])
            assert migrated['document_count']==original_count
            for kind in ['application','acknowledgment','irs_filed','irs_acceptance']:assert latest['documents'][kind]==original[kind]
            (OUT/'reopened-confirmation.pdf').write_bytes(get(latest['documents']['confirmation_screen']))
            page.locator('#tnClose').click()
            # The Yes path requests an upload; it never displays the new-form fields.
            go('global');prepare();page.locator('#tnIRSAnswer').select_option('yes')
            assert page.locator('#tnSupportUpload').count()==1;assert page.locator('#irs_ein').count()==0
            page.get_by_text('Demo documents',exact=True).click();page.locator('#tnUseDemoEvidence').click()
            page.get_by_text('CO number and matching test attachment added automatically.',exact=False).wait_for()
            assert page.get_by_text('Download matching test packet',exact=True).count()==0
            page.screenshot(path=str(OUT/'YES-EXISTING-IRS-AUTOMATIC-ATTACHMENT.png'),full_page=True)
            page.locator('#tnReviewed').check();page.locator('#tnAuthorized').check();drop_submit['once']=True;page.locator('#tnSubmitDemo').click()
            page.get_by_text('Receipt acknowledged — Demo only',exact=True).wait_for(timeout=12000)
            global_request=next(x for x in json.loads(get('/__state'))['requests'] if x['ein']=='521273585')
            assert global_request['state_sends']==1,'Lost HTTP response must reconcile, never resend'
            assert not errors,errors
            assert '/__public' not in network,'A fresh signed main result must avoid the duplicate public lookup'
            (OUT/'BROWSER-CONTRACT.json').write_text(json.dumps({'passed':True,'reused_fresh_main_result_without_public_lookup':True,'reason_statement_filename_explicit':True,'live_network_requests':0,'main_results_nonblocking':True,'first_request_no_federal_step_or_deadline':True,'first_request_test_submission':True,'second_both_test_submits':True,'second_synthetic_fixture_explicit':True,'closed_state_window_disabled':True,'automatic_co_and_file':True,'displayed_test_confirmation_captured':True,'delayed_receipt_polled':True,'five_document_links_persist':True,'links_hidden_until_check':True,'repeated_check_creates_no_files':True,'no_download_upload_loop':True,'actual_lost_http_response_reconciled_without_duplicate':True,'page_errors':errors,'browser_requests':len(network)},indent=2))
            browser.close()
    finally:server.shutdown();thread.join()
    print('PASS: local actual-browser workflow, both test submits, confirmation image, delayed receipt, persistence and Yes upload; zero live traffic.')

if __name__=='__main__':main()
