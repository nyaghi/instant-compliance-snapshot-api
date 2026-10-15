"""Fresh public entity-number/blank-type fixture; offline, no live-speed claim."""
import copy,json,time,unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as cc

FIXTURE=json.loads((Path(__file__).parent/'fixtures/nv-untyped-entity-number-20261015.json').read_text(encoding='utf-8'))
HEADERS=['Filed Date','Effective Date','Filing Number','Filing Type','Source','No. of Pages']
class AsOf(date):
    @classmethod
    def today(cls):return cls(2026,10,15)

class UntypedEntityNumberControls(unittest.TestCase):
    def setUp(self):
        for key,kw in [('date',{'new':AsOf}),('trial_identity',{'return_value':{'label':'trial'}}),
                       ('reconciled_registry_address',{'return_value':{'decision':'not_available'}})]:
            p=patch.object(cc,key,**kw);p.start();self.addCleanup(p.stop)

    def lookup(self,*,fields=None,history=True,rows=None,complete=True,filing_rows=None):
        fields=copy.deepcopy(fields or FIXTURE['fields']);identifier=FIXTURE['fields']['Entity Number'];calls=[]
        row=dict(name=fields['Entity Name'],identifier=identifier,entity_number=identifier,
                 business_identifier_missing=True,entity_type='',raw_status='Registered')
        def provider(q):
            calls.append(q)
            if q['operation']=='search':
                selected=copy.deepcopy([row] if rows is None else rows)
                return dict(query=q,state='NV',complete=complete,verification_pending=False,total=len(selected),rows=selected)
            result=dict(query=q,complete=True,fields=fields,source_url=FIXTURE['source_url'])
            if history:result['filings']=dict(identifier=identifier,name=fields['Entity Name'],headers=HEADERS,
                rows=copy.deepcopy(FIXTURE['filing_rows'] if filing_rows is None else filing_rows),total=1,complete=True)
            return result
        with patch.object(cc,'licensed_charity_names',return_value=([fields['Entity Name']],[])):
            result=cc.final_four_browser_lookup(cc.checker.Organization(fields['Entity Name'],'720408946'),'NV',provider,time.monotonic()+10)
        return result,calls

    def test_current_untyped_entity_number_and_independent_organization_use_actual_exemption(self):
        for name in [FIXTURE['fields']['Entity Name'],'Independent Community Education Foundation']:
            result,calls=self.lookup(fields={**FIXTURE['fields'],'Entity Name':name,'IRS Registered Name':name})
            self.assertEqual(result.status,'Exempt');self.assertEqual(result.matched_registry_identifier,FIXTURE['fields']['Entity Number'])
            self.assertTrue(any(q['operation']=='detail' for q in calls));self.assertIn('source-confirmed exemption filing',result.source_note)

    def test_explicit_csr_category_does_not_supply_status_without_complete_filing_history(self):
        result,_=self.lookup(history=False);self.assertEqual(result.status,'Unable to Confirm')
        result,_=self.lookup(filing_rows=[['02/20/2026','02/20/2026','123','Annual List','Email','1']])
        self.assertEqual(result.status,'Unable to Confirm','Solicits Yes and a corporate annual list do not supply exemption evidence')

    def test_conflicting_ein_identity_type_and_business_id_never_confirm(self):
        result,_=self.lookup(fields={**FIXTURE['fields'],'FEIN':'131624103'})
        self.assertNotEqual(result.status,'Exempt');self.assertFalse(getattr(result,'matched_registry_identifier',''))
        for changes in [{'Entity Number':'E76543212026-2'},{'NV Business ID':'NV20261234567'},
                        {'Entity Type':'Registered Agent'},{'Entity Type':'Domestic Limited Liability Company (86)'},{'Entity Type':''}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.lookup(fields={**FIXTURE['fields'],**changes})

    def test_untyped_search_requires_exact_number_loaded_status_and_missing_id_flag(self):
        row=dict(name=FIXTURE['fields']['Entity Name'],identifier=FIXTURE['fields']['Entity Number'],
                 entity_number=FIXTURE['fields']['Entity Number'],business_identifier_missing=True,entity_type='',raw_status='Registered')
        for changes in [{'raw_status':''},{'entity_number':''},{'entity_number':'E76543212026-2'},
                        {'business_identifier_missing':False},{'identifier':'bogus'}]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.lookup(rows=[{**row,**changes}])

    def test_completed_no_record_and_incomplete_search_keep_their_distinct_meaning(self):
        result,calls=self.lookup(rows=[]);self.assertEqual(result.status,'Not Registered')
        self.assertTrue(all(q['operation']=='search' for q in calls))
        with self.assertRaises(ValueError):self.lookup(complete=False)

    def test_untyped_entity_number_survives_signed_continuation(self):
        from testing.run_final_four_continuation_guardrails import ContinuationControls
        h=ContinuationControls();h.setUp()
        try:
            fields=FIXTURE['fields'];identifier=fields['Entity Number'];h.orgs['NV']=cc.checker.Organization(fields['Entity Name'],'720408946')
            with patch.object(cc,'licensed_charity_names',return_value=([fields['Entity Name']],[])):
                code,response=h.start('NV',alternate_names=[fields['Entity Name']])
                for _ in range(8):
                    if response.get('phase')!='search':break
                    q=response['query']
                    if q['operation']=='search':evidence=dict(query=q,state='NV',complete=True,verification_pending=False,total=1,rows=[dict(name=fields['Entity Name'],identifier=identifier,entity_number=identifier,business_identifier_missing=True,entity_type='',raw_status='Registered')])
                    else:evidence=dict(query=q,complete=True,fields=fields,source_url=FIXTURE['source_url'],filings=dict(identifier=identifier,name=fields['Entity Name'],headers=HEADERS,rows=FIXTURE['filing_rows'],total=1,complete=True))
                    code,response=h.advance(response,evidence)
            self.assertEqual(code,200);self.assertEqual(response['phase'],'complete');self.assertEqual(response['result']['status'],'Exempt')
        finally:h.doCleanups()

if __name__=='__main__':unittest.main()
