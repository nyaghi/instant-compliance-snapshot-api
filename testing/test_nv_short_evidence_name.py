"""Typed Nevada names must survive response formatting and exact archive binding."""
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from deployment.state_snapshots import matching_reference


class ShortEvidenceName(unittest.TestCase):
    def result(self, name='P4L', ein='204235269', state='NV', status='Delinquent'):
        org = cc.checker.Organization('Lemonade Day — P4L', ein)
        r = cc.checker.StateResult(org.organization_name, ein, state, status, '')
        r.success = True
        r.matched_registry_name = name
        r.matched_registry_identifier = 'NV20181082642'
        return org, r

    def format(self, org, r):
        cc.fill_registry_match_from_text(r, '', org)
        cc.normalize_registry_match_fields(r, org)
        return dict(ein=org.ein, state=r.state, matched_registry_name=r.matched_registry_name,
                    matched_registry_identifier=r.matched_registry_identifier)

    def setUp(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({'204235269': ('P4L', 'Lemonade Day')})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset, token)

    def test_reviewed_source_name_keeps_exact_archive_link(self):
        org, r = self.result()
        ref = dict(ein=org.ein, state='NV', identifier=r.matched_registry_identifier,
                   record_name='P4L', operation='detail', url='local-proof.pdf')
        formatted = self.format(org, r)
        self.assertEqual(r.matched_registry_name, 'P4L')
        self.assertEqual(r.status, 'Delinquent')
        self.assertIs(matching_reference(formatted, [ref]), ref)
        for field, value in [('ein', '987654321'), ('state', 'WI'),
                             ('identifier', 'different'), ('record_name', 'P4L Foundation')]:
            with self.subTest(field=field):
                self.assertIsNone(matching_reference(formatted, [{**ref, field: value}]))

    def test_short_names_require_reviewed_identity_for_this_ein(self):
        for name, ein in [('PFL', '204235269'), ('P4', '204235269'),
                          ('DBA', '204235269'), ('INC', '204235269'),
                          ('123', '204235269'), ('P4L', '987654321')]:
            with self.subTest(name=name, ein=ein):
                org, r = self.result(name, ein)
                self.format(org, r)
                self.assertNotEqual(r.matched_registry_name, name)

    def test_free_text_noise_filter_is_unchanged(self):
        self.assertEqual(cc.useful_registry_name('P4L'), '')
        org, r = self.result('')
        cc.fill_registry_match_from_text(r, 'Organization Name: P4L Status: Expired', org)
        self.assertNotEqual(r.matched_registry_name, 'P4L')

    def test_incomplete_and_negative_identity_stays_cleared(self):
        for status in ['Not Registered', 'Site Not Reachable', 'Unable to Verify', 'Unable to Confirm']:
            org, r = self.result(status=status)
            self.format(org, r)
            self.assertEqual((r.matched_registry_name, r.matched_registry_identifier), ('', ''))

    def test_thirty_reviewed_short_identity_contexts(self):
        for i in range(30):
            ein = str(100000000+i); name = 'A'+str(i).zfill(2)
            token = cc.REVIEWED_NAME_CONTEXT.set({ein: (name,)})
            try:
                org, r = self.result(name, ein)
                self.format(org, r)
                self.assertEqual(r.matched_registry_name, name)
            finally:
                cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_all_states_preserve_reviewed_typed_names_without_changing_status(self):
        states='AL AK AR CA CO CT DC FL GA HI IL KS KY LA ME MD MA MI MN MS NV NH NJ NM NY NC ND OH OK OR PA RI SC TN VA WA WV WI'.split()
        for state in states:
            for status in ['Current','Upcoming Filing','Delinquent','Exempt','Revoked / Suspended']:
                with self.subTest(state=state,status=status):
                    org,r=self.result(state=state,status=status)
                    data=self.format(org,r)
                    self.assertEqual(r.matched_registry_name,'P4L')
                    self.assertEqual(r.status,status)
                    ref=dict(ein=org.ein,state=state,identifier=r.matched_registry_identifier,
                             record_name='P4L',operation='detail',url='fixture.pdf')
                    self.assertIs(matching_reference(data,[ref]),ref)
                    self.assertIsNone(matching_reference(data,[{**ref,'record_name':'P4L unrelated'}]))

    def test_all_states_reject_unreviewed_short_names_and_clear_negative_identity(self):
        states='AL AK AR CA CO CT DC FL GA HI IL KS KY LA ME MD MA MI MN MS NV NH NJ NM NY NC ND OH OK OR PA RI SC TN VA WA WV WI'.split()
        for state in states:
            for name in ['PFL','DBA','INC','123']:
                org,r=self.result(name=name,state=state)
                self.format(org,r)
                self.assertNotEqual(r.matched_registry_name,name)
            for status in ['Not Registered','Unable to Confirm','Unable to Verify','Site Not Reachable']:
                org,r=self.result(state=state,status=status)
                self.format(org,r)
                self.assertEqual((r.matched_registry_name,r.matched_registry_identifier),('',''))


if __name__ == '__main__':
    unittest.main()
