"""User-approved trial Nevada entity-standing rule, isolated from mature rules."""
import unittest
from unittest.mock import patch
from datetime import date
import registry_snapshot_server as cc
from testing.run_final_four_source_guardrails import NV, NV_SOLICITATION, AsOf, LookupControls

class NevadaDisplayedDate(unittest.TestCase):
    def setUp(self):
        for name,value in [('trial_identity',{'label':'trial'}),('date',AsOf)]:
            p=patch.object(cc,name,return_value=value) if name=='trial_identity' else patch.object(cc,name,value)
            p.start();self.addCleanup(p.stop)

    def record(self, **fields):
        return cc.nv_charity_detail_evidence({**NV,**fields},NV['NV Business ID'])

    def test_displayed_date_controls_without_history(self):
        for deadline,status in [('12/31/2026','Upcoming Filing'),('12/31/2027','Current'),('08/31/2026','Delinquent')]:
            with self.subTest(deadline=deadline):
                row=self.record(**{'Annual Renewal Due Date/Expiration Date':deadline})
                self.assertEqual(row['status'],status)
                self.assertFalse(row['requires_solicitation_history'])
                self.assertIsNone(row['initial']);self.assertIsNone(row['renewal'])
                self.assertIsNone(row['entity_formation'])

    def test_missing_date_is_inconclusive_not_current_or_negative(self):
        for value in ['','-']:
            self.assertEqual(self.record(**{'Annual Renewal Due Date/Expiration Date':value})['status'],'Unable to Confirm')
        with self.assertRaises(ValueError):self.record(**{'Annual Renewal Due Date/Expiration Date':'loading'})

    def test_adverse_status_survives_future_or_missing_date(self):
        for raw,status in [('Revoked','Revoked'),('Default','Delinquent'),('Inactive','Closed / Withdrawn / Canceled'),('Withdrawn','Closed / Withdrawn / Canceled')]:
            for deadline in ['','12/31/2027']:
                self.assertEqual(self.record(**{'Entity Status':raw,'Annual Renewal Due Date/Expiration Date':deadline})['status'],status)

    def test_registered_category_uses_displayed_date(self):
        row=cc.nv_charity_detail_evidence(NV_SOLICITATION,NV_SOLICITATION['NV Business ID'])
        self.assertEqual(row['status'],'Current')

    def test_unrelated_formation_date_does_not_gate_renewal(self):
        self.assertEqual(self.record(**{'Formation Date in Nevada':'not loaded'})['status'],'Upcoming Filing')

    def test_identity_and_entity_type_guards_remain(self):
        for changes in [{'NV Business ID':'NV99999999'},{'Entity Type':'Registered Agent'},{'FEIN':'123'}]:
            with self.assertRaises(ValueError):self.record(**changes)

    def test_full_lookup_omits_history_and_preserves_comment_basis(self):
        fixture=LookupControls();fixture.setUp();self.addCleanup(fixture.doCleanups)
        def provider(query):
            payload=fixture.provider(query)
            payload.pop('filings',None)
            return payload
        with patch.object(cc,'nv_charity_filings_evidence',side_effect=AssertionError('History must not be read')):
            result=cc.final_four_browser_lookup(fixture.orgs['NV'],'NV',provider)
            self.assertTrue(result.success);self.assertEqual(result.status,'Upcoming Filing')
            self.assertEqual(result.matched_registry_identifier,NV['NV Business ID'])
            self.assertIn("nonprofit corporation's Nevada record",result.source_note)
            self.assertNotIn('source-confirmed filing history',result.source_note)
            # Older connector evidence must not change the approved trial scope.
            previous=cc.final_four_browser_lookup(fixture.orgs['NV'],'NV',fixture.provider)
            self.assertEqual(previous.status,result.status)

    def test_completed_negative_and_transport_failure_remain_distinct(self):
        fixture=LookupControls();fixture.setUp();self.addCleanup(fixture.doCleanups)
        def empty(query):
            return {**fixture.provider(query),'rows':[],'total':0}
        result=cc.final_four_browser_lookup(fixture.orgs['NV'],'NV',empty)
        self.assertEqual(result.status,'Not Registered')
        with self.assertRaises(TimeoutError):
            cc.final_four_browser_lookup(fixture.orgs['NV'],'NV',lambda query: (_ for _ in ()).throw(TimeoutError('Detail did not load')))

    def test_mature_scope_unchanged(self):
        with patch.object(cc,'trial_identity',return_value=None):
            row=self.record()
            self.assertTrue(row['requires_solicitation_history']);self.assertEqual(row['status'],'Unable to Confirm')

if __name__=='__main__':unittest.main()
