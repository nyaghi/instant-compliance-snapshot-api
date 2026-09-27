"""Native FL forms preserve complete response, updated viewstate and identity."""
import ast,os,subprocess,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs
import registry_snapshot_server as m


def strip_native_forms(tree):
    fn=next((n for n in tree.body if getattr(n,'name','')=='lab_fl_form_context_options'),None)
    if fn is None:return
    tree.body.remove(fn)
    expected=ast.parse('context_kwargs.update(lab_fl_form_context_options(state, org))').body[0]
    removed=[]
    for node in ast.walk(tree):
        for _,body in ast.iter_fields(node):
            if not isinstance(body,list):continue
            for item in list(body):
                if isinstance(item,ast.AST) and ast.dump(item)==ast.dump(expected):body.remove(item);removed.append(item)
    assert len(removed)==1


class NativeForms(unittest.TestCase):
    def test_only_explicit_lab_sales_florida_without_evidence(self):
        base={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_FL_SCRIPTLESS':'1'}
        for state,mode,version,override,evidence,want in [
            ('FL','sales','x-performance-lab',{},False,True),
            ('FL','standard','x-performance-lab',{},False,False),
            ('CO','sales','x-performance-lab',{},False,False),
            ('FL','sales','staging',{},False,False),
            ('FL','sales','x-performance-lab',{'PUBLIC_BASE_URL':'https://staging.compliance-express.com'},False,False),
            ('FL','sales','x-performance-lab',{'CE_LAB_FL_SCRIPTLESS':''},False,False),
            ('FL','sales','x-performance-lab',{},True,False)]:
            with self.subTest(state=state,mode=mode,version=version,override=override,evidence=evidence),patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{**base,**override}),patch.object(m,'CAPTURE_EVIDENCE_SCREENSHOTS',False),patch.object(m,'CAPTURE_LIGHTWEIGHT_SOURCE_SNAPSHOT',False):
                token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:self.assertEqual(m.lab_fl_form_context_options(state,SimpleNamespace(evidence_mode=evidence)),{'java_script_enabled':False} if want else {})
                finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_remaining_master_is_identical_to_deployed_74(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','cb0021a:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_native_forms(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

    def test_browser_posts_updated_viewstate_and_preserves_every_query(self):
        with m.checker.sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                for final,expected in [('record','Current'),('empty','Not Registered'),('incomplete','Site Not Reachable')]:
                    with self.subTest(final=final):
                        context=browser.new_context(java_script_enabled=False)
                        page=context.new_page();requests=[]
                        def reply(route):
                            req=route.request;fields=parse_qs(req.post_data or '')
                            requests.append((req.method,fields))
                            text='No records found'
                            if len(requests)>2:
                                text={'record':'<table><tr><td>Example Relief Inc</td><td>License/Registration Number CH12345 Expiration Date 12/31/2027 Status Current</td></tr></table>',
                                      'empty':'No records found','incomplete':'Registry response incomplete'}[final]
                            html='<html><body><script>window.pageScriptRan=true;</script><form method="post" action="./CheckACharity.aspx"><input type="hidden" name="__VIEWSTATE" value="v'+str(len(requests))+'"><input name="ctl00$cpMainContent$BusinessNameTb"><input type="submit" name="ctl00$cpMainContent$SingleSearchBt" value="Search"></form>'+text+'</body></html>'
                            route.fulfill(status=200,content_type='text/html',body=html)
                        page.route('**/*',reply)
                        with patch.object(m,'fl_business_lookup_enabled',return_value=False),patch.object(m,'reviewed_queries_first',return_value=['Old Example Relief','Example Relief Inc']),patch.object(m.time,'sleep'):
                            result=m.search_fl(page,SimpleNamespace(organization_name='Example Relief Inc',ein='123456789'))
                        self.assertIsNone(page.evaluate('window.pageScriptRan'))
                        self.assertEqual(m.public_status(result),expected)
                        self.assertEqual([r[0] for r in requests],['GET','POST','POST'])
                        self.assertEqual(requests[2][1]['__VIEWSTATE'],['v2'])
                        self.assertEqual(requests[2][1]['ctl00$cpMainContent$BusinessNameTb'],['Example Relief Inc'])
                        if final=='record':self.assertEqual(result.matched_registry_identifier,'CH12345')
                        if final=='incomplete':self.assertFalse(result.success)
                        context.close()
            finally:browser.close()


if __name__=='__main__':unittest.main()
