"""Local browser test of actual UI + service. Every request is intercepted to
an isolated in-memory HTTP test service; no live staging/IRS/state traffic.
"""
import base64,io,json,os,threading,urllib.request
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright,expect
from deployment import tn_extensions_demo as t
from testing.test_tn_extensions_demo import Accounts,ACCOUNT,NOW

ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('CC_TN_TEST_OUTPUT',str(ROOT/'testing/tn-workflow-evidence')));OUT.mkdir(parents=True,exist_ok=True)
ORIGIN='https://charityclarity-final-four-29-2.onrender.com'
ORG={'fcc':('680412350','Foundation for California Community Colleges'),'boston':('042774441',"Children's Hospital Corporation"),'global':('521273585','Global Impact'),'closed':('521125072','Society for Scholarly Publishing')}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,body,kind='application/json',status=200):
        if not isinstance(body,bytes):body=json.dumps(body).encode()
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def setup_service(self):
        if not hasattr(self.server,'accounts'):self.server.accounts=Accounts();self.server.offset=0;self.server.calls=[]
        return t.Service(self.server.accounts),self.server.accounts.c
    def do_GET(self):
        service,c=self.setup_service();path=urlsplit(self.path).path
        if path.startswith(t.PREFIX+'/documents/'):
            row=c.execute('SELECT body FROM cc_tn_extension_demo_documents WHERE id=%s AND account=%s',(path.rsplit('/',1)[-1],ACCOUNT)).fetchone()
            return self.send(bytes(row['body']),'application/pdf') if row else self.send({},status=404)
        if path in ['/tn-extensions-demo.js','/tn-extensions-demo.css','/tn-extension-portal-rehearsal.js']:
            return self.send((ROOT/'web-staging'/path[1:]).read_bytes(),'text/javascript' if path.endswith('.js') else 'text/css')
        if path=='/__advance':self.server.offset=17;return self.send({'offset':17})
        if path=='/__old_capture':
            row=c.execute('SELECT data FROM cc_tn_extension_demo_requests WHERE account=%s AND ein=%s',(ACCOUNT,'042774441')).fetchone()
            r=row['data'];r['confirmation_capture']['format_version']=1;service.save(c,ACCOUNT,r,NOW+self.server.offset);c.db.commit();return self.send({'test_only_old_capture':True})
        if path=='/__state':
            rows=c.execute('SELECT data FROM cc_tn_extension_demo_requests WHERE account=%s',(ACCOUNT,)).fetchall()
            return self.send({'requests':[r['data'] for r in rows],'calls':self.server.calls,'document_count':c.execute('SELECT count(*) AS n FROM cc_tn_extension_demo_documents').fetchone()['n']})
        key=parse_qs(urlsplit(self.path).query).get('case',['fcc'])[0];identifier,name=ORG[key]
        result=dict(state='TN',ein=identifier,organization_name=name,status='Upcoming Filing')
        html='''<!doctype html><html><head><meta charset="utf-8"><title>Local isolated Tennessee workflow test</title><style>*,::before,::after{box-sizing:border-box}p,h1,h2,h3{margin:0}h1,h2,h3{font-weight:inherit;font-size:inherit}</style><link rel="stylesheet" href="/tn-extensions-demo.css"></head><body style="font:16px Arial;margin:24px"><h1>CharityClarity local test — Demo only</h1><p id="mainReady">Main results ready</p><section id="resultPanel"><table><tbody id="resultRows"><tr><td>Tennessee</td><td>Upcoming Filing</td><td></td></tr></tbody></table></section><script src="/tn-extension-portal-rehearsal.js"></script><script src="/tn-extensions-demo.js"></script><script>CCTennesseeExtensions.render(REPLACE_RESULT)</script></body></html>'''
        return self.send(html.replace('REPLACE_RESULT',json.dumps([result])).encode(),'text/html')
    def do_POST(self):
        service,c=self.setup_service()
        p=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.calls.append({'action':p.get('action'),'ein':p.get('ein'),'id':p.get('id')})
        try:
            with c.db:result=service.dispatch(c,ACCOUNT,p,NOW+self.server.offset)
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
                page.locator('#tnCheckExtensions').click();page.locator('#tnFileExtension').wait_for()
            def prepare():
                page.locator('#tnFileExtension').click();page.locator('#tnInitialPrior').select_option('no');page.locator('#tnPrepareExtension').click();page.locator('#tnIRSAnswer').wait_for()
            go('fcc');assert 'may be eligible' in page.locator('.tn-extension-row').inner_text()
            assert 'registration is Active' in page.locator('.tn-extension-row').inner_text()
            prepare();page.locator('#tnIRSAnswer').select_option('no');page.locator('#irs_ein').wait_for()
            assert page.locator('#irs_ein').input_value()=='680412350';assert page.locator('#tnSupportUpload').count()==0
            assert page.locator('#tnSubmitIRS').is_disabled();page.locator('#tnDownloadDraftIRS').click();page.get_by_role('link',name='View draft Form 8868 — Demo only').wait_for()
            page.screenshot(path=str(OUT/'FCC-PAST-FEDERAL-DEADLINE.png'),full_page=True)
            page.locator('#tnClose').click()
            go('closed');assert page.locator('#tnFileExtension').is_disabled()
            go('boston');prepare();page.locator('#tnIRSAnswer').select_option('no')
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
            page.locator('#tnSample8868').click();page.locator('#tnTestDownload a').wait_for();packet=get(page.locator('#tnTestDownload a').get_attribute('href'))
            page.locator('#tnSupportUpload').set_input_files({'name':'matching-demo-packet.pdf','mimeType':'application/pdf','buffer':packet})
            page.locator('#tnUploadSupport').click();page.get_by_text('CO number and matching test attachment added automatically.',exact=False).wait_for()
            page.screenshot(path=str(OUT/'YES-EXISTING-IRS-AUTOMATIC-ATTACHMENT.png'),full_page=True)
            page.locator('#tnReviewed').check();page.locator('#tnAuthorized').check();drop_submit['once']=True;page.locator('#tnSubmitDemo').click()
            page.get_by_text('Receipt acknowledged — Demo only',exact=True).wait_for(timeout=12000)
            global_request=next(x for x in json.loads(get('/__state'))['requests'] if x['ein']=='521273585')
            assert global_request['state_sends']==1,'Lost HTTP response must reconcile, never resend'
            assert not errors,errors
            (OUT/'BROWSER-CONTRACT.json').write_text(json.dumps({'passed':True,'live_network_requests':0,'main_results_nonblocking':True,'fcc_no_path_prefilled_without_upload':True,'past_federal_submission_blocked':True,'closed_state_window_disabled':True,'eligible_both_submits':True,'automatic_co_and_file':True,'displayed_test_confirmation_captured':True,'delayed_receipt_polled':True,'five_document_links_persist':True,'links_hidden_until_check':True,'repeated_check_creates_no_files':True,'yes_path_requires_matching_upload':True,'actual_lost_http_response_reconciled_without_duplicate':True,'page_errors':errors,'browser_requests':len(network)},indent=2))
            browser.close()
    finally:server.shutdown();thread.join()
    print('PASS: local actual-browser workflow, both test submits, confirmation image, delayed receipt, persistence and Yes upload; zero live traffic.')

if __name__=='__main__':main()
