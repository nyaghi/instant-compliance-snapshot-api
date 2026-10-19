"""Retained real identities with modeled source variants; no live-search claim."""
import copy, html, json, sys, time, unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
from testing import run_final_four_continuation_guardrails as signed_controls

COHORT=json.loads((Path(__file__).parent/'fixtures/oct19-cohort.json').read_text())[:30]
RECEIPTS={}
class Today(date):
    @classmethod
    def today(cls):return cls(2026,10,19)

class SurgicalControls(unittest.TestCase):
    def setUp(self):
        for name,value in [('date',Today),('known_names_for_ein',[]),('reconciled_registry_address',{'decision':'corroborated'})]:
            p=patch.object(c,name,value if name=='date' else None) if name=='date' else patch.object(c,name,return_value=value)
            p.start();self.addCleanup(p.stop)
        p=patch.object(c.urllib.request,'urlopen',side_effect=AssertionError('Local control attempted unmodeled network'))
        p.start();self.addCleanup(p.stop)

    def test_or_thirty_full_adapter_status_date_comment_controls(self):
        passed=[]
        cases=[('6/30/2025','11/15/2026','Upcoming Filing'),('12/31/2024','5/15/2026','Delinquent'),('12/31/2025','5/15/2027','Current')]
        for ctx in COHORT:
            with self.subTest(organization=ctx['name']):
                org=c.checker.Organization(ctx['name'],ctx['ein'])
                for end,due,status in cases:
                    raw=f'Status: Registered | Latest Report Year: 2024 | Fiscal Year End: {end} | Next Due: {due}'
                    ext=SimpleNamespace(status=status,raw_status_text=raw,success=True,matched_registry_name=ctx['registry_name'],matched_registry_identifier='69938',source_url='https://justice.oregon.gov/Charities/Charity/details?charityID=80579')
                    r=c.copy_external_result(org,'OR',ext)
                    self.assertEqual(r.status,status)
                    self.assertEqual(c.true_status_from_body(r,raw),status)
                    self.assertEqual(c.parse_due_date(r.computed_due_date),c.parse_due_date(due))
                    comment=c.comments_for_result(r,raw,status)
                    self.assertIn('Live Oregon record checked:',comment)
                    self.assertNotIn('Base Due from Latest Report Period',r.raw_status_text)
                    # The live worker supplies the full official page body,
                    # whose old Report Year label triggered a second override.
                    body=f'{ctx["name"]} Federal EIN: {ctx["ein"]} Status: Registered Reports 2024 Fiscal Year Beginning 7/1/2024 and Ending {end} Report Year: 2024'
                    public=c.response_data_for_lookup(r,body,org,org.organization_name,org.ein,'OR',time.perf_counter())
                    self.assertEqual(public['status'],status)
                    self.assertEqual(c.parse_due_date(public['computed_due_date']),c.parse_due_date(due))
                passed.append(ctx['ein'])
        RECEIPTS['OR']=passed

    def test_or_adverse_and_unverified_next_due_not_promoted(self):
        for standing in ['Suspended','Revoked','Withdrawn','Closed','Exempt']:
            raw=f'Status: {standing} | Latest Report Year: 2024 | Fiscal Year End: 6/30/2025 | Next Due: 11/15/2026'
            self.assertEqual(c.classify_or_latest_report_status(raw),'')
            self.assertIsNone(c.or_completed_report_next_due(raw))

    def test_or_actual_failed_worker_full_body_through_execute(self):
        from deployment.queue_engine import execute
        retained=json.loads((Path(__file__).parent/'fixtures/oct19-or-full-body.json').read_text(encoding='utf-8'))
        source=retained['result'];name=source['organization_name'];ein=source['ein']
        def lookup(organization_name,formatted_ein,state):
            org=c.checker.Organization(organization_name,formatted_ein)
            ext=SimpleNamespace(**source)
            result=c.copy_external_result(org,'OR',ext)
            return c.response_data_for_lookup(result,retained['body'],org,organization_name,formatted_ein,state,time.perf_counter())
        job={'state':'OR','version':c.APP_VERSION,'payload':{'ein':ein,'organization_name':name,'alternate_names':[],'mode':'standard'}}
        with patch.object(c,'run_single_state_lookup_reliably',side_effect=lookup):
            out=execute(c,job)
        self.assertEqual(out['status'],'Upcoming Filing')
        self.assertEqual(c.parse_due_date(out['computed_due_date']),date(2026,11,15))
        self.assertEqual(out['status_reason'],'OR_STATUS_FROM_COMPLETED_LIVE_REPORT')
        self.assertIn('Live Oregon record checked:',out['comments'])
        self.assertNotIn('downloadable',out['comments'].lower())
        for raw in ['Status: Registered | Latest Report Year: 2024 | Fiscal Year End: 6/30/2030 | Next Due: 11/15/2031',
                    'Status: Registered | Latest Report Year: 2024 | Fiscal Year End: 6/30/2025 | Next Due: 11/15/2031',
                    'Status: Registered | Fiscal Year End: 6/30/2025 | Next Due: 11/15/2026']:
            self.assertIsNone(c.or_completed_report_next_due(raw))

    def test_dc_thirty_full_identity_controls_and_foreign_ein_guards(self):
        passed=[]
        for ctx in COHORT:
            with self.subTest(organization=ctx['name']):
                name=ctx['name']; org=c.checker.Organization(name,ctx['ein'])
                source={'name':name+' (THE)','identifier':'modeled-license','status':'Delinquent','raw_status':'Expired - Enforcement','expiration':date(2024,4,30),'location':'','aliases':[]}
                self.assertEqual(c.licensed_charity_identity(org,source,'DC',time.monotonic()+3),'accepted')
                self.assertEqual(source['name'],name+' (THE)')
                foreign={**source,'ein':'99-9999999'}
                self.assertEqual(c.licensed_charity_identity(org,foreign,'DC',time.monotonic()+3),'rejected')
                self.assertNotEqual(c.licensed_charity_identity(org,{**source,'name':name+' Separate Regional Chapter (THE)'},'DC',time.monotonic()+3),'accepted')
                passed.append(ctx['ein'])
        RECEIPTS['DC']=passed

    def test_dc_reported_reviewed_alias_placement(self):
        org=c.checker.Organization('William & Mary Foundation','54-0734117')
        tok=c.REVIEWED_NAME_CONTEXT.set({'540734117':['THE COLLEGE OF WILLIAM & MARY FOUNDATION']})
        try:
            row={'name':'COLLEGE OF WILLIAM & MARY FOUNDATION (THE)','identifier':'70103543','status':'Delinquent','raw_status':'Expired - Enforcement','location':'Williamsburg, VA'}
            with patch.object(c,'known_names_for_ein',side_effect=lambda ein: ['THE COLLEGE OF WILLIAM & MARY FOUNDATION'] if c.canonical_ein_digits(ein)=='540734117' else []):
                self.assertEqual(c.licensed_charity_identity(org,row,'DC',time.monotonic()+3),'accepted')
        finally:c.REVIEWED_NAME_CONTEXT.reset(tok)

    def test_sc_thirty_primary_versus_historical_alias_workflows(self):
        passed=[]
        for ctx in COHORT:
            with self.subTest(organization=ctx['name']):
                primary=ctx['name']; name=primary+', Inc.'
                alias=primary+' Research Foundation'
                calls=[]
                class Response:
                    def __init__(self,text):self.text=text
                    def raise_for_status(self):pass
                session=SimpleNamespace(headers={})
                session.get=lambda *a,**kw:Response('<form></form>')
                literal=c.literal_name_retrieval_forms(name)[0]
                def post(url,data,**kw):
                    identifier=data.get('ctl00$MainContent$Hidden_CharityID')
                    if identifier:
                        return Response('Public Id: P'+identifier+' Status: '+('Registered Due Date: 11/15/2026' if identifier=='641' else 'Terminated'))
                    query=data['ctl00$MainContent$txt_CharitySearchName'];calls.append(query)
                    rows=[('641',primary),('10980',alias)] if query.casefold()==literal.casefold() else [('10980',alias)]
                    return Response(''.join(f'<a href="javascript:CharityInfo({i})">{html.escape(n)}</a>' for i,n in rows))
                session.post=post
                with patch.object(c,'known_names_for_ein',side_effect=lambda ein: [alias] if c.canonical_ein_digits(ein)==c.canonical_ein_digits(ctx['ein']) else []),patch.object(c.curl_requests,'Session',return_value=session),patch.object(c,'sc_detail_filing_ein',side_effect=lambda source,*args,**kw: c.canonical_ein_digits(ctx['ein']) if 'P641' in source else '999999999'):
                    result=c.sc_official_detail_lookup(c.checker.Organization(name,ctx['ein']))
                self.assertEqual(result.matched_registry_identifier,'P641')
                self.assertEqual(result.status,'Upcoming Filing')
                self.assertEqual([q.casefold() for q in calls],[literal.casefold()])
                passed.append(ctx['ein'])
        RECEIPTS['SC']=passed

    def test_freshness_thirty_actual_organization_results(self):
        passed=[]
        info={'downloaded_at':'2026-10-19T01:19:51+00:00','source_date':'','usable':True}
        for ctx in COHORT:
            with self.subTest(organization=ctx['name']),patch.object(c,'downloadable_data_info',return_value=info):
                r=c.checker.StateResult(ctx['name'],ctx['ein'],'OR','Current','https://justice.oregon.gov/charities',raw_status_text='Status: Registered',success=True)
                comment=c.comments_for_result(r,'','Current')
                self.assertIn('October 18, 2026 at 09:19 PM EDT',comment)
                self.assertIn('State source date: not stated by source',comment)
                self.assertNotIn('2026-10-19T',comment)
                passed.append(ctx['ein'])
        RECEIPTS['freshness']=passed
        for stamp,expected in [('2026-01-02T01:00:00Z','January 01, 2026 at 08:00 PM EST'),('2026-07-02T01:00:00Z','July 01, 2026 at 09:00 PM EDT')]:
            self.assertEqual(c.freshness_display_time(stamp),expected)
        for stamp in ['','bad','2026-10-19T01:00:00']:
            self.assertEqual(c.freshness_display_time(stamp),'unverified')

    def test_nc_thirty_source_rows_retain_identity_scope_and_dates(self):
        passed=[]
        for ctx in COHORT:
            with self.subTest(organization=ctx['name']):
                card={'CSL Legal Name':ctx['name'],'CSL Type':'In-Process','Status':'Expired Inactive','License':'','Expiration Date':'','profile_url':'https://www.sosnc.gov/online_services/search/charities_profile/123456'}
                row=c.nc_charity_record_evidence(card)
                self.assertEqual(row['status'],'Unable to Confirm')
                self.assertTrue(row['unsupported_registration_scope'])
                self.assertEqual(row['identifier'],'NCAPP-123456')
                for changes in [{'Expiration Date':'11/15/2027'},{'Extension End Date':'11/15/2027'},{'CSL Type':'Unknown'},{'profile_url':'https://evil.test/123456'}]:
                    with self.assertRaises(ValueError):c.nc_charity_record_evidence({**card,**changes})
                passed.append(ctx['ein'])
        RECEIPTS['NC-fields']=passed

    def test_nc_thirty_signed_empty_searches_do_not_stop_on_unrelated_inactive_card(self):
        passed=[]
        for ctx in COHORT:
            with self.subTest(organization=ctx['name']):
                t=signed_controls.ContinuationControls('test_all_four_complete_through_signed_master_replay');t.setUp()
                try:
                    t.orgs['NC']=c.checker.Organization(ctx['name'],ctx['ein'])
                    with patch.object(c,'licensed_charity_names',return_value=([ctx['name']],[])):
                        code,res=t.start('NC')
                        for _ in range(12):
                            if res.get('phase')!='search':break
                            q=res['query'];self.assertEqual(q['operation'],'search')
                            card={'CSL Legal Name':'Unrelated American Legion Auxiliary Unit','CSL Type':'In-Process','Status':'Expired Inactive','License':'','Expiration Date':'','profile_url':'https://www.sosnc.gov/online_services/search/charities_profile/123456'}
                            evidence={'state':'NC','query':q,'complete':True,'verification_pending':False,'search_mode':q.get('search_mode','STARTS_WITH'),'total':1,'rows':[card]}
                            code,res=t.advance(res,evidence=evidence)
                    self.assertEqual(code,200);self.assertEqual(res['phase'],'complete')
                    self.assertEqual(res['result']['status'],'Not Registered')
                    passed.append(ctx['ein'])
                finally:t.doCleanups()
        RECEIPTS['NC-signed']=passed

class OklahomaControls(unittest.TestCase):
    def test_thirty_actual_org_inputs_historical_trade_names_are_not_equivalent_live_records(self):
        passed=[]
        with c.checker.sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            try:
                page=browser.new_page()
                for ctx in COHORT:
                    with self.subTest(organization=ctx['name']):
                        name=ctx['name'];org=c.checker.Organization(name,ctx['ein'])
                        rows=[('4300712772',name,'Legal In use'),('4300599099',name,'Tradename Inactive'),('4300599099',name+' Local Chapter','Legal Former')]
                        for ordered in (rows,list(reversed(rows))):
                            markup='<table>'+''.join(f'<tr><td><a href="charityDetail.aspx?id={i}">{i}</a></td><td>{html.escape(n)}</td><td>Charitable Organization</td><td></td><td>{status}</td></tr>' for i,n,status in ordered)+'</table>'
                            page.set_content(markup)
                            with patch.object(c,'known_names_for_ein',return_value=[]):
                                chosen=c.ok_choose_safe_result_row_on_page(page,org,None)
                            self.assertEqual(chosen[3],'4300712772')
                            self.assertEqual(org.ok_equivalent_records,[(name,'4300712772')])
                        passed.append(ctx['ein'])
                page.close()
            finally:browser.close()
        RECEIPTS['OK']=passed

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]))
    Path(__file__).with_suffix('.receipt.json').write_text(json.dumps({'mode':'local actual code, retained real inputs, modeled source contexts','distinct_inputs':len({x['ein'] for x in COHORT}),'passed':{k:len(set(v)) for k,v in RECEIPTS.items()},'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},indent=2),encoding='utf-8')
    sys.exit(not result.wasSuccessful())
