"""Duplicate registration selection after identity confirmation; no registry I/O."""
import copy
import time
import unittest
from datetime import date
from unittest.mock import patch
import registry_snapshot_server as cc


class LicensedDbaDuplicateControls(unittest.TestCase):
    def rows(self, legal='Beacon Literacy Network', trade='ReadTogether'):
        return [dict(name=legal, identifier='old', status='Closed / Withdrawn / Canceled',
                     raw_status='Withdrawn', expiration=date(2021, 7, 31), ein=''),
                dict(name=f'{legal} dba {trade}', identifier='new', status='Delinquent',
                     raw_status='Expired', expiration=date(2023, 3, 31), ein='')]

    def select(self, rows, *, outcomes=None):
        # Isolate duplicate selection after the identity layer; no primary-name preference.
        org=cc.checker.Organization('Submitted Composite Organization','123456789')
        def identity(org,row,state,deadline):
            row['address_evidence']={'decision':'unavailable'}
            row['match']={'decision':'accepted','reason':'MATCH_REVIEWED_ALTERNATE_NAME'}
            return (outcomes or {}).get(row['identifier'],'accepted')
        with patch.object(cc,'licensed_charity_identity',side_effect=identity):
            return cc.select_licensed_charity(org,copy.deepcopy(rows),'NV',time.monotonic()+5)

    def test_explicit_same_legal_dba_uses_later_period_after_identity(self):
        for legal,trade in [('Beacon Literacy Network','ReadTogether'),
                            ('United Animal Nations','RedRover'),
                            ('Harbor Habitat Alliance','GreenFuture')]:
            with self.subTest(legal=legal):
                chosen,review=self.select(self.rows(legal,trade))
                self.assertEqual(review,'')
                self.assertEqual(chosen['identifier'],'new')

    def test_related_or_former_names_remain_ambiguous(self):
        for other in ['Beacon Literacy Network Foundation dba ReadTogether',
                      'Beacon Literacy Network West Chapter dba ReadTogether',
                      'Beacon Literacy Network formerly ReadTogether',
                      'Beacon Literacy Network / ReadTogether']:
            rows=self.rows(); rows[1]['name']=other
            chosen,review=self.select(rows)
            self.assertIsNone(chosen)
            self.assertIn('identities could not be distinguished',review)

    def test_reported_case_through_real_identity_selector_with_reviewed_names(self):
        org=cc.checker.Organization('United Animal Nations — RedRover','680124097')
        rows=self.rows('UNITED ANIMAL NATIONS','RedRover')
        token=cc.REVIEWED_NAME_CONTEXT.set({'680124097':['UNITED ANIMAL NATIONS','UNITED ANIMAL NATIONS DBA REDROVER']})
        try:
            with patch.object(cc,'reconciled_registry_address',return_value={'decision':'unavailable'}):
                chosen,review=cc.select_licensed_charity(org,rows,'NV',time.monotonic()+5)
            self.assertEqual(review,'')
            self.assertEqual(chosen['identifier'],'new')
            self.assertEqual(chosen['status'],'Delinquent')
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_unconfirmed_candidate_is_not_promoted(self):
        chosen,review=self.select(self.rows(),outcomes={'new':'possible'})
        self.assertEqual(chosen['identifier'],'old')
        chosen,review=self.select(self.rows(),outcomes={'old':'possible','new':'possible'})
        self.assertIsNone(chosen)

    def test_conflicting_eins_and_short_legal_names_cannot_resolve_duplicates(self):
        for changes in [{'ein':'987654321'}, {'name':'BLN dba ReadTogether'}]:
            rows=self.rows(); rows[0]['ein']='123456789'; rows[1].update(changes)
            chosen,review=self.select(rows)
            self.assertIsNone(chosen)

    def test_same_period_conflicting_status_and_revocation_guards_remain(self):
        rows=self.rows(); rows[0]['expiration']=rows[1]['expiration']
        chosen,review=self.select(rows)
        self.assertIsNone(chosen)
        self.assertIn('conflicting statuses',review)
        rows=self.rows(); rows[0].update(status='Current',expiration=date(2026,12,31))
        rows[1].update(status='Revoked',expiration=date(2027,12,31))
        chosen,review=self.select(rows)
        self.assertIsNone(chosen)
        self.assertIn('revocation',review)


if __name__=='__main__': unittest.main()
