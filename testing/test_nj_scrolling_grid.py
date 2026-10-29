"""Local Chromium replay of the official NJ scrolling grid, not live searches."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import registry_snapshot_server as m

URL = 'https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/'
API = 'https://charportal.dca.njoag.gov/_services/entity-grid-data.json/test-grid'
SOURCE = Path(__file__).parent/'fixtures/nj_cancer_scrolling_grid.json'


def source_pages():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    fields = [('name',0),('accountnumber',2),('crsm_filestanding',3),('crsm_federalein',4),
              ('crsm_addressline1',5),('crsm_mailingcity',6),('crsm_mailingstate',7),('crsm_mailingzip',8)]
    # Pages 1/2 are transport fixtures reconstructed from the actual visible rows.
    # Pages 3/4/5 are retained native responses, including original record IDs.
    records = [{'Id':'local-replay-'+str(i), 'Attributes':[
        {'Name':key,'Value':row[index],'DisplayValue':row[index]} for key,index in fields]}
        for i,row in enumerate(source['rows'])]
    pages = [{'Records':records[i:i+10], 'ItemCount':42,'PageNumber':i//10+1,
              'PageCount':5,'PageSize':10,'MoreRecords':i+10<42} for i in range(0,42,10)]
    for page in source['observed_pages']:
        pages[page['PageNumber']-1]=page
    return pages


HTML = '''<input placeholder="Search"><div class="public-search-grid" style="height:180px;overflow:auto">No records to show</div>
<script>
const box=document.querySelector('input'),grid=document.querySelector('.public-search-grid');
let query='',number=0,more=false,busy=false;
async function load(reset=false){
 if(busy || (!reset && !more))return; busy=true;
 const n=reset?1:number+1;
 const r=await fetch('/_services/entity-grid-data.json/test-grid',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({search:query,page:n})});
 const data=await r.json();
 setTimeout(()=>{
  if(reset){grid.innerHTML='';grid.scrollTop=0;}
  for(const record of data.Records){const row=document.createElement('div');row.setAttribute('role','row');row.style.height='45px';row.textContent=record.Attributes.map(a=>a.DisplayValue).join(' ');grid.append(row);}
  if(!data.Records.length)grid.textContent='No records to show';
  number=n;more=data.MoreRecords;busy=false;
 },75);
}
box.onkeydown=e=>{if(e.key==='Enter'){query=box.value;load(true);}};
grid.onscroll=()=>{if(grid.scrollTop+grid.clientHeight>=grid.scrollHeight-2)load();};
</script>'''

# The real first page has no inner overflow. Its last row must enter the
# browser viewport before page two creates an internal scrollbar.
DOCUMENT_HTML = HTML.replace('<input placeholder="Search">','<div style="height:300px"></div><input placeholder="Search">').replace('height:180px','height:545px').replace(
    "number=n;more=data.MoreRecords;busy=false;",
    "number=n;more=data.MoreRecords;busy=false; observer.disconnect(); if(more)observer.observe(grid.lastElementChild);")
DOCUMENT_HTML = DOCUMENT_HTML.replace("box.onkeydown=e=>", "const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))load();}); box.onkeydown=e=>")


class ScrollingGrid(unittest.TestCase):
    def setUp(self):
        self.org=m.checker.Organization('United Cancer Front','954865948')

    def request(self,data,number,query='Cancer'):
        req=Mock(url=API,method='POST',post_data_json={'search':query,'page':number})
        res=req.response.return_value
        res.url=API;res.status=200;res.headers={'content-type':'application/json'};res.json.return_value=data
        return req

    def test_actual_pages_are_bound_and_all_42_excluded_only_after_completion(self):
        pages=source_pages()
        for i,page in enumerate(pages,1):
            self.assertEqual(len(m.nj_completed_query_rows(self.request(page,i),'Cancer',i)),len(page['Records']))
            self.assertIsNone(m.nj_completed_query_rows(self.request(page,i),'wrong',i))
        for count in range(1,5):
            self.assertFalse(m.nj_complete_grid_excludes_org(m.nj_join_query_pages(pages[:count]),self.org))
        joined=m.nj_join_query_pages(pages)
        self.assertEqual(len(joined['Records']),42)
        self.assertTrue(m.nj_complete_grid_excludes_org(joined,self.org))

    def test_page_and_identity_rejection_controls(self):
        pages=source_pages()
        malformed=[[],[None],pages[1:],pages+[pages[-1]],pages[:1]+pages[2:]]
        for key,value in [('ItemCount',43),('PageNumber',1),('PageSize',20),('PageCount',4),('MoreRecords',False),('Success',False),('Error','changed')]:
            changed=copy.deepcopy(pages);changed[1][key]=value;malformed.append(changed)
        repeated=copy.deepcopy(pages);repeated[1]['Records'][0]['Id']=repeated[0]['Records'][0]['Id'];malformed.append(repeated)
        for case in malformed:self.assertIsNone(m.nj_join_query_pages(case))
        for name,ein in [('Unrelated',self.org.ein),(self.org.organization_name,'954865940'),(self.org.organization_name,'')]:
            changed=copy.deepcopy(pages)
            row=changed[-1]['Records'][-1]
            for a in row['Attributes']:
                if a['Name']=='name':a['Value']=a['DisplayValue']=name
                if a['Name']=='crsm_federalein':a['Value']=a['DisplayValue']=ein
            self.assertFalse(m.nj_complete_grid_excludes_org(m.nj_join_query_pages(changed),self.org))

    def browser_case(self,browser,pages,org=None,malform_page=None,stale=False,document_scroll=False):
        page=browser.new_page();requests=[]
        def route(r):
            if r.request.url==URL:r.fulfill(status=200,content_type='text/html',body=DOCUMENT_HTML if document_scroll else HTML)
            elif r.request.url==API:
                n=r.request.post_data_json['page'];requests.append(n)
                data=copy.deepcopy(pages[n-1])
                if n==malform_page:data['PageCount']=99
                if stale and n==2:
                    # A failed response cannot be replaced by the previous grid.
                    r.fulfill(status=503,body='Unavailable');return
                r.fulfill(status=200,content_type='application/json',body=json.dumps(data))
            else:r.abort()
        page.route('**/*',route)
        try:
            body=m.nj_search_body(page,'Cancer',identity_org=org)
            return body,copy.deepcopy(getattr(page,'_cc_nj_completed_data',None)),requests,copy.deepcopy(page._cc_nj_query_diagnostic)
        finally:page.close()

    def test_chromium_30_identity_contexts_and_first_page_candidate_parity(self):
        pages=source_pages()
        with m.checker.sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                for i in range(30):
                    org=self.org if i==0 else m.checker.Organization('Retained Control '+str(i),str(100000000+i))
                    body,data,requests,diag=self.browser_case(browser,pages,org,document_scroll=(i%2==0))
                    self.assertIsNotNone(body,diag);self.assertEqual(requests,[1,2,3,4,5])
                    self.assertEqual(len(data['Records']),42)
                    self.assertTrue(m.nj_complete_grid_excludes_org(data,org))
                    self.assertIn('CANCER VACCINE COALITION',body)
                # The original positive route must not acquire additional pages.
                first=pages[0]['Records'][0]
                attrs={a['Name']:a['DisplayValue'] for a in first['Attributes']}
                org=m.checker.Organization(attrs['name'],attrs['crsm_federalein'])
                body,data,requests,diag=self.browser_case(browser,pages,org)
                self.assertIsNotNone(body);self.assertEqual(requests,[1]);self.assertTrue(data['MoreRecords'])
                body,data,requests,diag=self.browser_case(browser,pages)
                self.assertIsNotNone(body);self.assertEqual(requests,[1])
                body,data,requests,diag=self.browser_case(browser,pages,self.org,malform_page=2)
                self.assertIsNone(body);self.assertEqual(diag['phase'],'inconsistent_grid_pages')
                body,data,requests,diag=self.browser_case(browser,pages,self.org,stale=True)
                self.assertIsNone(body);self.assertIsNone(data)
            finally:browser.close()


if __name__=='__main__':unittest.main()
