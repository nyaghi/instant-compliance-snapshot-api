"""Offline replay of observed NC SL exempt markup through actual collector/parser."""
import os,unittest
from pathlib import Path
import registry_snapshot_server as m

SOURCE=Path(os.environ['CC_CANDIDATE_CONNECTOR'])/'registry-content.js'
URL='https://www.sosnc.gov/online_services/search/charities_profile/12411115'
# Observed profile's identity, exemption, application and address markup.
HTML='''<main><h1>CSL Exempt Organization</h1><section>
<div class="para-small"><span class="boldSpan">Name:</span>&nbsp;&nbsp;The Scripps Research Institute</div>
<div class="para-small"><span class="boldSpan">Address</span><div class="para-small"><span>10550 N Torrey Pines Rd</span><br><span>La Jolla</span>, <span>CA</span>&nbsp;<span>92037-1000</span></div></div>
<div class="para-small"><span class="boldSpan">Status:</span>&nbsp;&nbsp;CSL Exempt</div>
<div class="para-small"><span class="boldSpan">Registration #:&nbsp;</span>SL010345</div>
<div class="para-small"><span class="boldSpan">501c Type:</span>&nbsp;&nbsp;501(c)(3) Charitable Organization</div>
<div class="para-small"><span class="boldSpan">CSL Exemption Type:</span>&nbsp;&nbsp;131F-3(4) Educational Institution</div>
<div class="para-small"><span class="boldSpan"> Last Application Date:</span>&nbsp;&nbsp;1/14/2022</div>
<div class="para-small"><a href="/online_services/search/charities_filings/12411115">Document Filings</a></div>
</section></main>'''

class Profile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=m.checker.sync_playwright().start();cls.browser=cls.p.chromium.launch(headless=True)
        source=SOURCE.read_text(encoding='utf-8')
        cls.js="const text=el=>(el?.innerText||'').replace(/\\s+/g,' ').trim();"+source[source.index('  function ncLabeled('):source.index('  let ncSubmissionStarted')]+source[source.index('  function ncProfile('):source.index('  function ncFilings(')]
    @classmethod
    def tearDownClass(cls):cls.browser.close();cls.p.stop()
    def setUp(self):
        self.context=self.browser.new_context();self.addCleanup(self.context.close)
        self.page=self.context.new_page();self.markup=HTML
        self.page.route('**/*',lambda r:r.fulfill(status=200,content_type='text/html',body=self.markup) if r.request.url==URL else r.abort())
    def collect(self,html=HTML,identifier='SL010345'):
        self.markup=html;self.page.goto(URL)
        return self.page.evaluate('(query)=>{'+self.js+';return ncProfile(query)}',{'url':URL,'identifier':identifier})
    def test_actual_sl_exempt_profile_reaches_existing_master_exemption_rule(self):
        output=self.collect();fields=output['evidence']['fields']
        self.assertEqual(fields['Expiration Date'],'');self.assertEqual(fields['Street'],'10550 N Torrey Pines Rd')
        card={'identifier':'SL010345','name':'The Scripps Research Institute','license_category':'CSL Exempt Organization','url':URL,'raw_status':'CSL Exempt'}
        result=m.nc_charity_profile_evidence(card,fields)
        self.assertEqual(result['status'],'Exempt');self.assertEqual(result['identifier'],'SL010345')
        self.assertIsNone(result['expiration'])
        for changed in [{'Name':'Foreign Institute'},{'Registration #':'SL999999'},{'profile_url':URL+'9'}]:
            with self.assertRaises(ValueError):m.nc_charity_profile_evidence(card,{**fields,**changed})
    def test_actual_collector_profile_survives_signed_wire_and_original_archive(self):
        import base64,tempfile,time
        from unittest.mock import patch
        from deployment import state_snapshots as snapshots
        from testing.run_final_four_continuation_guardrails import ContinuationControls
        fields=self.collect()['evidence']['fields']
        harness=ContinuationControls('test_all_four_complete_through_signed_master_replay')
        harness.setUp();self.addCleanup(harness.doCleanups)
        name='The Scripps Research Institute';harness.orgs['NC']=m.checker.Organization(name,'330435954')
        card={'CSL Legal Name':name,'CSL Type':'CSL Exempt Organization','Status':'CSL Exempt',
            'License':'SL010345','Expiration Date':'','Extension End Date':'','profile_url':URL}
        with tempfile.TemporaryDirectory() as folder:
            store=snapshots.SQLiteStore(Path(folder)/'nc.sqlite')
            with patch.object(snapshots,'STORE',store),patch.object(m,'licensed_charity_names',return_value=([name],[])), \
                 patch.object(m,'licensed_charity_foreign_ein',return_value={}):
                code,response=harness.start('NC');self.assertEqual(code,200)
                operations=[]
                for _ in range(20):
                    if response.get('phase')!='search':break
                    query=response['query'];operations.append(query['operation']);extra={}
                    if query['operation']=='search':
                        evidence={'state':'NC','query':query,'complete':True,'verification_pending':False,
                            'total':1,'rows':[card],'search_mode':query.get('search_mode','STARTS_WITH')}
                    elif query['operation']=='detail':
                        evidence={'query':query,'complete':True,'fields':fields}
                        extra['state_snapshot']={'query':query,'source_url':URL,'public_text':self.page.locator('body').inner_text(),
                            'captured_at':time.time(),'image':base64.b64encode(self.page.screenshot()).decode()}
                    elif query['operation']=='filings':
                        evidence={'query':query,'complete':True,'url':query['url'],'rows':[{'type':'Exemption Request','date':'1/14/2022'}]}
                    else:self.fail(query)
                    code,response=harness.advance(response,evidence=evidence,**extra)
                    self.assertEqual(code,200,response)
                self.assertEqual(response['phase'],'complete',response)
                self.assertEqual(response['result']['status'],'Exempt',response)
                self.assertIn('detail',operations)
                self.assertTrue(response['result'].get('evidence_url'),response['result'])
    def test_missing_dates_remain_rejected_without_explicit_exempt_profile(self):
        for markup in [HTML.replace('<h1>CSL Exempt Organization</h1>','<h1>Organization</h1>'),
                HTML.replace('CSL Exemption Type:','Unrecognized Type:'),
                HTML.replace('CSL Exempt</div>','Denied</div>'),
                HTML.replace('Last Application Date:','Other Date:'),
                HTML.replace('The Scripps Research Institute</div>','</div>')]:
            with self.subTest(markup=markup[:60]),self.assertRaises(Exception):self.collect(markup)
        with self.assertRaises(Exception):self.collect(identifier='SL999999')
    def test_existing_ex_and_current_profiles_remain_accepted(self):
        self.assertTrue(self.collect(HTML.replace('SL010345','EX010345'),identifier='EX010345')['ok'])
        self.assertTrue(self.collect(HTML.replace('CSL Exempt</div>','Current Active</div>'))['ok'])
        dated=HTML.replace('</section>','<div class="para-small"><span class="boldSpan">Expiration Date:</span>1/31/2027</div></section>')
        self.assertEqual(self.collect(dated)['evidence']['fields']['Expiration Date'],'1/31/2027')

if __name__=='__main__':unittest.main()
