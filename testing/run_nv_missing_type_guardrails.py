"""Observed blank public grid type / explicit charity-detail category, offline."""
import copy,json,unittest
from pathlib import Path
from datetime import date
from unittest.mock import patch
import registry_snapshot_server as cc

CASES=json.loads((Path(__file__).parent/'fixtures/nv-public-type-gap-20261015.json').read_text(encoding='utf-8'))['cases']
class AsOf(date):
    @classmethod
    def today(cls):return cls(2026,10,15)

class NevadaMissingTypeControls(unittest.TestCase):
    def setUp(self):
        token=cc.REVIEWED_NAME_CONTEXT.set({c['ein']:[c['fields']['Entity Name']] for c in CASES})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset,token)
        for name,kwargs in [('date',{'new':AsOf}),('trial_identity',{'return_value':{'origin':'https://fixture.onrender.com'}}),
                            ('reconciled_registry_address',{'return_value':{'decision':'not_available'}}),
                            ('licensed_charity_street_evidence',{'return_value':None})]:
            p=patch.object(cc,name,**kwargs);p.start();self.addCleanup(p.stop)

    def lookup(self,c,*,fields=None,rows=None,complete=True):
        calls=[]
        rowdata=rows if rows is not None else [dict(name=r[0],identifier=r[1],entity_number=r[2],entity_type=r[3],raw_status=r[6]) for r in c['rows']]
        def provider(q):
            calls.append(q)
            if q['operation']=='search':return dict(state='NV',query=q,complete=complete,verification_pending=False,total=len(rowdata),rows=copy.deepcopy(rowdata))
            self.assertEqual(q['identifier'],c['fields']['NV Business ID'],'unrelated LLC must not be opened')
            return dict(query=q,complete=True,fields=copy.deepcopy(fields if fields is not None else c['fields']),source_url=c['source_url'])
        with patch.object(cc,'licensed_charity_names',return_value=([c['fields']['Entity Name']],[])):
            result=cc.final_four_browser_lookup(cc.checker.Organization(c['organization_name'],c['ein']),'NV',provider)
        return result,calls

    def test_reported_cases_retrieve_missing_grid_type_from_verified_detail(self):
        for c in CASES:
            with self.subTest(organization=c['organization_name']):
                result,calls=self.lookup(c)
                self.assertEqual(result.status,c['expected'])
                self.assertEqual(result.matched_registry_identifier,c['fields']['NV Business ID'])
                self.assertEqual(len([q for q in calls if q['operation']=='detail']),1)
                self.assertIn('charitable-solicitation registration statement',result.source_note)
                self.assertNotIn("nonprofit corporation's Nevada record",result.source_note)

    def test_explicit_charity_type_is_also_supported_when_grid_supplies_it(self):
        c=CASES[1];r=c['rows'][0]
        result,_=self.lookup(c,rows=[dict(name=r[0],identifier=r[1],entity_type=c['fields']['Entity Type'],raw_status=r[6])])
        self.assertEqual(result.status,'Current')

    def test_unsupported_detail_type_or_changed_name_or_id_stays_unconfirmed(self):
        c=CASES[0]
        for update in [{'Entity Type':'Foreign Corporation (80)'},{'Entity Name':'An unrelated foundation'},
                       {'NV Business ID':'NV20261234567'},{'Entity Type':''}]:
            with self.subTest(update=update),self.assertRaises(ValueError):self.lookup(c,fields={**c['fields'],**update})

    def test_blank_grid_type_requires_loaded_status_and_observed_entity_number(self):
        c=CASES[0];r=c['rows'][0]
        for update in [{'raw_status':''},{'raw_status':None},{'entity_number':''},{'entity_number':'invalid'},
                       {'identifier':'1234'},{'business_identifier_missing':True}]:
            row=dict(name=r[0],identifier=r[1],entity_type='',raw_status=r[6],entity_number=r[2]);row.update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):self.lookup(c,rows=[row])

    def test_incomplete_grid_never_becomes_a_negative_or_a_confirmed_registration(self):
        with self.assertRaises(ValueError):self.lookup(CASES[0],complete=False)

    def test_completed_empty_search_remains_negative_without_detail_requests(self):
        result,calls=self.lookup(CASES[0],rows=[])
        self.assertEqual(result.status,'Not Registered')
        self.assertTrue(all(q['operation']=='search' for q in calls))

    def test_conflicting_detail_ein_cannot_confirm_the_requested_organization(self):
        result,_=self.lookup(CASES[0],fields={**CASES[0]['fields'],'FEIN':'12-3456789'})
        self.assertNotIn(result.status,{'Current','Upcoming Filing','Delinquent','Exempt'})

    def test_missing_type_and_charity_detail_survive_signed_continuation(self):
        from testing.run_final_four_continuation_guardrails import ContinuationControls
        for c in CASES:
            h=ContinuationControls();h.setUp()
            try:
                h.orgs['NV']=cc.checker.Organization(c['organization_name'],c['ein'])
                with patch.object(cc,'licensed_charity_names',return_value=([c['fields']['Entity Name']],[])):
                    code,response=h.start('NV',alternate_names=[c['fields']['Entity Name']])
                    for _ in range(8):
                        if response.get('phase')!='search':break
                        q=response['query']
                        if q['operation']=='search':
                            rows=[dict(name=r[0],identifier=r[1],entity_number=r[2],entity_type=r[3],raw_status=r[6]) for r in c['rows']]
                            evidence=dict(state='NV',query=q,complete=True,verification_pending=False,total=len(rows),rows=rows)
                        else:evidence=dict(query=q,complete=True,fields=c['fields'],source_url=c['source_url'])
                        code,response=h.advance(response,evidence)
                self.assertEqual(code,200);self.assertEqual(response['phase'],'complete')
                self.assertEqual(response['result']['status'],c['expected'])
            finally:h.doCleanups()

if __name__=='__main__':unittest.main()
