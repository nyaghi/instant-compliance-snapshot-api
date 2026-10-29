"""HI typed-name retention and NJ complete-grid detail admission regressions.

Local source/transport fixtures; not live state searches.
"""
import ast
import copy
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import registry_snapshot_server as m
from deployment.state_snapshots import matching_reference
from testing.capacity_lab.test_nj_complete_grid import row, grid

ROOT = Path(m.__file__).parent


class HawaiiTypedName(unittest.TestCase):
    def setUp(self):
        self.org = m.checker.Organization('Lemonade Day — P4L', '204235269')
        token = m.REVIEWED_NAME_CONTEXT.set({self.org.ein: ('P4L', 'Lemonade Day')})
        self.addCleanup(m.REVIEWED_NAME_CONTEXT.reset, token)
        # Minimal structural replay of independently viewed public detail fields.
        self.source = ('<html><h1>P4L dba Lemonade Day</h1><dl>'
            '<dt>Primary Name:</dt><dd>P4L dba Lemonade Day</dd>'
            '<dt>FEIN:</dt><dd>20-4235269</dd>'
            '<dt>Registration Status:</dt><dd>Active</dd>'
            '<dt>Registration Type:</dt><dd>Registered</dd></dl>'
            '<h2>Documents</h2></html>')
        self.url = 'https://charity.ehawaii.gov/charity/204235269/details.html'

    def parse(self, source=None, org=None):
        with patch.object(m, 'hi_public_filing_period', return_value={}):
            return m.hi_direct_details_from_source(org or self.org, source or self.source, self.url)

    def test_observed_dba_short_name_survives_formatter_and_archive_binding(self):
        r, body = self.parse()
        m.fill_registry_match_from_text(r, body, self.org)
        m.normalize_registry_match_fields(r, self.org)
        self.assertEqual(r.matched_registry_name, 'P4L')
        self.assertEqual(r.raw_status_text, 'Registration Status: Active | Registration Type: Registered')
        ref = dict(ein=self.org.ein, state='HI', identifier='20-4235269',
                   record_name='P4L', operation='detail', url='fixture.pdf')
        data = dict(ein=self.org.ein, state='HI', matched_registry_name=r.matched_registry_name,
                    matched_registry_identifier=r.matched_registry_identifier)
        self.assertIs(matching_reference(data, [ref]), ref)
        for key, value in [('ein','987654321'),('state','NV'),('record_name','Unrelated'),('identifier','different')]:
            self.assertIsNone(matching_reference(data, [{**ref, key:value}]))

    def test_missing_duplicate_wrong_identity_and_unreviewed_short_names_reject(self):
        cases = [self.source.replace('20-4235269', '20-4235260'),
                 self.source.replace('FEIN:', 'Missing:'),
                 self.source.replace('</dl>', '<dt>Primary Name:</dt><dd>P4L</dd></dl>'),
                 self.source.replace('</html>', ''), self.source.replace('Documents','Missing'),
                 self.source.replace('P4L dba Lemonade Day', 'XYZ')]
        for source in cases:
            with self.subTest(source=source): self.assertIsNone(self.parse(source))

    def test_thirty_short_identity_and_six_status_contexts(self):
        for i in range(30):
            ein=str(100000000+i); name='A'+str(i).zfill(2)
            token=m.REVIEWED_NAME_CONTEXT.set({ein:(name,)})
            try:
                org=m.checker.Organization('Reviewed organization '+str(i),ein)
                for status in ['Active','Inactive','Expired','Pending','Suspended','Revoked']:
                    source=self.source.replace('20-4235269',ein).replace('P4L dba Lemonade Day',name).replace('Active',status)
                    r,_=self.parse(source,org)
                    self.assertEqual(r.matched_registry_name,name)
                    self.assertEqual(r.status,status)
            finally: m.REVIEWED_NAME_CONTEXT.reset(token)


class NewJerseyGridAdmission(unittest.TestCase):
    def setUp(self):
        self.org=m.checker.Organization('Lemonade Day — P4L','204235269')
        self.query=SimpleNamespace(organization_name='PFL',ein='')
        token=m.REVIEWED_NAME_CONTEXT.set({self.org.ein:('P4L','Lemonade Day','PFL')})
        self.addCleanup(m.REVIEWED_NAME_CONTEXT.reset,token)

    def execute(self,data,identity=True,body='PFLAG MORRISTOWN-MORRIS COUNTY INC CH12345'):
        page=SimpleNamespace(_cc_nj_completed_data=data)
        with patch.object(m,'nj_search_body',return_value=body), \
             patch.object(m,'nj_name_exemption_result',return_value=None), \
             patch.object(m,'nj_detail_body',return_value='') as detail, \
             patch.object(m,'nj_result_from_body',side_effect=lambda p,o,r,b,e:r):
            r=m.search_nj_direct(page,self.query,identity_org=self.org if identity else None)
        return r,detail.call_count

    def test_observed_unrelated_pflag_is_excluded_before_detail(self):
        r, calls=self.execute(grid([row('PFLAG MORRISTOWN-MORRIS COUNTY INC','393169244')]))
        self.assertEqual(calls,0)
        self.assertEqual(m.public_status(r),'Not Registered')
        self.assertTrue(r.success)

    def test_incomplete_grid_matching_identity_and_ein_conflict_keep_detail(self):
        good=grid([row()])
        cases=[None,{**good,'MoreRecords':True},{**good,'ItemCount':2},{**good,'PageNumber':2},
               grid([row('P4L',None)]),grid([row('P4L',self.org.ein)]),
               grid([row(self.org.organization_name,'204235260')]),grid([row('Unrelated',self.org.ein)])]
        for data in cases:
            with self.subTest(data=data): self.assertEqual(self.execute(data)[1],1)
        self.assertEqual(self.execute(good,identity=False)[1],1)
        r,calls=self.execute(good,body=None)
        self.assertEqual(calls,0)
        self.assertFalse(r.success)
        self.assertEqual(r.reason_code,'NJ_INCOMPLETE_QUERY_RESPONSE')

    def test_thirty_joined_name_plans_continue_after_unrelated_grid(self):
        for i in range(30):
            org=m.checker.Organization('Control Relief '+str(i),str(100000000+i))
            names=['PFL','Control Relief '+str(i)]
            page=SimpleNamespace();seen=[]
            def search(p,q):
                seen.append(q)
                if q==names[0]:
                    p._cc_nj_completed_data=grid([row('PFLAG MORRISTOWN-MORRIS COUNTY INC','393169244')])
                    return 'PFLAG MORRISTOWN-MORRIS COUNTY INC CH12345'
                p._cc_nj_completed_data=grid([])
                return 'No records found'
            with patch.object(m,'nj_same_lookup_zero_queries',return_value={org.ein}), \
                 patch.object(m,'nj_name_fallback_queries',return_value=names), \
                 patch.object(m,'nj_search_body',side_effect=search), \
                 patch.object(m,'nj_name_exemption_result',return_value=None), \
                 patch.object(m,'nj_detail_body',side_effect=AssertionError('Unrelated detail opened')):
                r=m.search_nj_with_name_fallback(page,org)
            self.assertEqual(seen,names)
            self.assertEqual(m.public_status(r),'Not Registered')
            self.assertEqual(r.queries_attempted,names)
            # A later incomplete response must never finalize that negative.
            def incomplete(p,q):
                if q==names[-1]: return None
                return search(p,q)
            with patch.object(m,'nj_same_lookup_zero_queries',return_value={org.ein}), \
                 patch.object(m,'nj_name_fallback_queries',return_value=names), \
                 patch.object(m,'nj_search_body',side_effect=incomplete), \
                 patch.object(m,'nj_name_exemption_result',return_value=None):
                r=m.search_nj_with_name_fallback(page,org)
            self.assertNotEqual(m.public_status(r),'Not Registered')
            self.assertFalse(r.success)


if __name__=='__main__': unittest.main()
