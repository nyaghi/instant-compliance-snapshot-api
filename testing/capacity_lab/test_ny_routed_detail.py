"""Same official route, original request deadline and unchanged identity rules."""
import ast,json,os,subprocess,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright
import registry_snapshot_server as m
from testing.capacity_lab.ny_route_scope import strip_ny_routed_detail

SOURCE='https://charities-search.ag.ny.gov/RegistrySearch'
SETTINGS={'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com',
          'CE_LAB_NY_ROUTED_DETAIL':'1','CE_LAB_NY_FAILED_REQUEST_WAKEUP':'1'}
HTML='''<html><body><a href="/RegistrySearch/04-31-23">04-31-23</a>
<a href="/RegistrySearch/12-34-56">12-34-56</a><script>
window.siteDetailInvocations=0;
addEventListener('popstate',()=>{
 const id=location.pathname.split('/')[2];
 if(id){window.siteDetailInvocations++;
 fetch('https://charities-search-api.ag.ny.gov/api/FileNet/RegistryDetail?orgID='+encodeURIComponent(id));}
});</script></body></html>'''

class BrowserRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.play=sync_playwright().start();cls.browser=cls.play.chromium.launch(headless=True)
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.play.stop()
    def setUp(self):
        self.page=self.browser.new_page();self.documents=0;self.detail_ids=[];self.status=200
        self.env=patch.dict(os.environ,SETTINGS);self.env.start();self.addCleanup(self.env.stop)
        self.version=patch.object(m,'APP_VERSION','fixture-performance-lab');self.version.start();self.addCleanup(self.version.stop)
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)
        self.page.route('**/*',self.route);self.page.goto(SOURCE)
        self.page._cc_ny_search_url=SOURCE
    def tearDown(self):self.page.close()
    def route(self,route):
        p=urlsplit(route.request.url)
        if p.hostname=='charities-search.ag.ny.gov':
            self.documents+=1;return route.fulfill(status=200,content_type='text/html',body=HTML)
        if p.hostname=='charities-search-api.ag.ny.gov' and p.path=='/api/FileNet/RegistryDetail':
            ident=parse_qs(p.query)['orgID'][0];self.detail_ids.append(ident)
            return route.fulfill(status=self.status,content_type='application/json',
                headers={'Access-Control-Allow-Origin':'https://charities-search.ag.ny.gov'},
                body=json.dumps({'data':{'orgID':ident,'ein':'123456789'}}))
        route.abort()
    def detail(self,ident='04-31-23'):
        return m.ny_browser_registry_response(self.page,'RegistryDetail',{'orgID':ident},2)
    def test_site_component_executes_each_detail_without_document_reload(self):
        first=self.detail();self.assertEqual(first.json()['data']['orgID'],'04-31-23')
        second=self.detail('12-34-56');self.assertEqual(second.json()['data']['orgID'],'12-34-56')
        self.assertEqual(self.detail_ids,['04-31-23','12-34-56'])
        self.assertEqual(self.documents,1)
        self.assertEqual(self.page.evaluate('siteDetailInvocations'),2)
    def test_state_rejection_is_preserved_without_extra_request_or_reload(self):
        self.status=403;r=self.detail()
        with self.assertRaisesRegex(RuntimeError,'403'):r.raise_for_status()
        self.assertEqual(r.json(),{});self.assertEqual(self.detail_ids,['04-31-23']);self.assertEqual(self.documents,1)
    def test_wrong_origin_path_id_query_and_fragment_are_rejected(self):
        for href in ['https://example.org/RegistrySearch/04-31-23','/RegistrySearch/99-99-99',
                     '/RegistrySearch/04-31-23?orgID=wrong','/RegistrySearch/04-31-23#wrong','javascript:void(0)']:
            self.page.locator('a').first.evaluate('(a,href)=>a.setAttribute("href",href)',href)
            with self.subTest(href=href),self.assertRaises(ValueError):self.detail()
        self.assertEqual(self.detail_ids,[]);self.assertEqual(self.documents,1)
    def test_duplicate_link_never_selects_first(self):
        self.page.locator('body').evaluate('(body)=>body.appendChild(body.querySelector("a").cloneNode(true))')
        with self.assertRaises(Exception):self.detail()
        self.assertEqual(self.detail_ids,[])
    def test_unknown_search_origin_does_not_route(self):
        self.page._cc_ny_search_url=SOURCE+'?unexpected=true'
        with self.assertRaises(ValueError):m.ny_open_registry_detail(self.page,'04-31-23',lambda:200)
        self.assertEqual(self.detail_ids,[])
    def test_missing_component_response_respects_original_budget(self):
        self.page.evaluate('window.stop(); history.pushState({}, "", location.href)')
        self.page.route('**/api/FileNet/RegistryDetail*',lambda route:route.abort('failed'))
        start=time.monotonic()
        with self.assertRaises(m.NYBrowserConnectionError):self.detail()
        self.assertLess(time.monotonic()-start,1)
        self.assertEqual(self.documents,1)

class GateAndScope(unittest.TestCase):
    def test_only_explicit_lab_sales_routes(self):
        for mode,version,change,want in [('sales','v-performance-lab',{},True),('standard','v-performance-lab',{},False),
            ('sales','production',{},False),('sales','v-performance-lab',{'CE_LAB_NY_ROUTED_DETAIL':''},False),
            ('sales','v-performance-lab',{'PUBLIC_BASE_URL':'https://staging.compliance-express.com'},False)]:
            with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{**SETTINGS,**change}):
                token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
                try:self.assertEqual(m.lab_ny_routed_detail(),want)
                finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)
    def test_standard_keeps_exact_original_click_and_timeout(self):
        page=Mock()
        with patch.object(m,'lab_ny_routed_detail',return_value=False):
            m.ny_open_registry_detail(page,'04-31-23',lambda:1234)
        page.get_by_role.assert_called_once_with('link',name='04-31-23',exact=True)
        page.get_by_role.return_value.click.assert_called_once_with(timeout=1234)
        page.evaluate.assert_not_called()
    def test_whole_master_verification_matching_retry_and_classification_unchanged(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','2e8d985:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_ny_routed_detail(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main(verbosity=2)
