"""A live exact-EIN/registration rename must not lose its original screenshot."""
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
import registry_snapshot_server as m
from deployment import source_visual_adapters as v
from testing import run_or_ma_live_period_guardrails as fixtures


class RenamedEvidence(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.Controls(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def produce(self,name='Prosper Global'):
        source=self.f.source.replace(self.f.org.organization_name,name)
        result,_=self.f.run_live(source)
        return result

    def admitted(self,data,row=None,adapter=v):
        run=SimpleNamespace(state='OR',ein='391383650',documents=[],visual_adapter_facts=[])
        master=SimpleNamespace(or_snapshot_row_for_ein=lambda ein:row or self.f.row,
            BROWSER_LOOKUP_SEMAPHORE=Mock(),checker=SimpleNamespace(sync_playwright=Mock(side_effect=RuntimeError('admitted'))))
        master.BROWSER_LOOKUP_SEMAPHORE.acquire.return_value=True
        adapter.capture_selected_source(master,data,run,time.monotonic()+60)
        return master.checker.sync_playwright.call_count

    def data(self,r):
        # Exercise the real transport allowlist rather than inserting the proof by hand.
        with patch.object(m,'enrich_registration_date_sources'),patch.object(m,'log_event'):
            return m.response_data_for_lookup(r,'',self.f.org,self.f.org.organization_name,self.f.org.ein,'OR',time.perf_counter())

    def test_live_rename_producer_transport_and_visual_admission(self):
        r=self.produce();data=self.data(r)
        self.assertEqual(data['matched_registry_name'],'Prosper Global')
        self.assertEqual(data['or_live_evidence']['source_identity'],{
            'ein':'391383650','registration':'19363','charity_id':'8122',
            'url':'https://justice.oregon.gov/Charities/Charity/details?charityID=8122'})
        self.assertEqual(self.admitted(data),1)

    def test_missing_or_mismatched_proof_keeps_rename_rejected(self):
        data=self.data(self.produce())
        cases=[{**data,'or_live_evidence':{}},{**data,'matched_registry_name':'Unrelated'}]
        for key,value in [('ein','123456789'),('registration','9'),('charity_id','8'),('url','https://example.com/')]:
            bad=copy.deepcopy(data);bad['or_live_evidence']['source_identity'][key]=value;cases.append(bad)
        for bad in cases:self.assertEqual(self.admitted(bad),0)
        row=list(self.f.row);row[4]='123456789';self.assertEqual(self.admitted(data,row),0)
        for status in ['Unable to Confirm','Not Registered','Site Not Reachable']:
            self.assertEqual(self.admitted({**data,'status':status}),0)

    def test_thirty_renamed_source_and_unchanged_original_name_contexts(self):
        for i in range(30):
            name='Confirmed New Name '+str(i)
            r=self.produce(name);data=self.data(r)
            self.assertEqual(data['matched_registry_name'],name)
            self.assertEqual(self.admitted(data),1)
            self.assertEqual(data['status'],'Current')
            original=self.data(self.produce(self.f.org.organization_name))
            original.pop('or_live_evidence')
            self.assertEqual(self.admitted(original),1)


if __name__=='__main__':unittest.main()
