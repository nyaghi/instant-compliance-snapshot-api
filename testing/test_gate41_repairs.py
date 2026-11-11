import copy
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock

import registry_snapshot_server as m
from deployment import gate41_repairs as g, state_snapshots as ss
from deployment.source_visual_adapters import wv_current_detail_binding

def d(s):
    return datetime.strptime(s,'%m/%d/%Y').date()

class Gate41(TestCase):
    def test_ct_service_retrieval_only_full_name(self):
        name='United Service Organizations Inc.'
        v=g.ct_service_variant(name)
        self.assertEqual(v,'United Services Organizations')
        plan=[name,'United Service Organizations','USO','Service']
        new=g.replace_low_value_slot(plan,[name],name,v)
        self.assertEqual(new,[name,'United Service Organizations','USO',v])
        for n in ('American Cancer Society','Service Dogs','United Service','Services International Fund'):
            self.assertEqual(g.ct_service_variant(n),'')

    def test_ga_exact_possessive_candidate_and_control_plans(self):
        org=m.checker.Organization('Khan Academy Inc.','261544963')
        with mock.patch.object(m,'known_names_for_ein',return_value=[]):
            req,gen=m.licensed_charity_names(org,literal_name_priority=True)
        actual=g.replace_low_value_slot(req+gen,req,req[0],g.ga_possessive_variant(req[0]))
        self.assertEqual(len(actual),len(req+gen))
        self.assertIn("Khan's Academy",actual)
        self.assertNotIn('Academy',actual)
        self.assertTrue(m.ga_possessive_candidate(org,'Khan’s Academy, Inc.'))
        for name in ("Khan's Academy Foundation","Khan's Academy of Georgia","Khan's Academies",'Khan Academy'):
            self.assertFalse(m.ga_possessive_candidate(org,name))
        for name in ('American Academy','National Institute','Beyond Celiac','American Cancer Society'):
            self.assertEqual(g.ga_possessive_variant(name),'')

    def test_ga_possessive_without_corroboration_requires_identity_review(self):
        org=m.checker.Organization('Khan Academy Inc.','261544963')
        base={'name':"Khan's Academy, Inc.",'identifier':'CH012769','ein':''}
        with mock.patch.object(m,'trial_identity',return_value=True), mock.patch.object(m,'known_names_for_ein',return_value=[]), mock.patch.object(m,'user_rejected_credential',return_value=False),mock.patch.object(m,'licensed_charity_street_evidence',return_value={}):
            for proof,outcome in [({},'possible'),({'decision':'corroborated'},'accepted'),({'decision':'different_ein'},'rejected')]:
                with mock.patch.object(m,'licensed_charity_foreign_ein',return_value=proof):
                    self.assertEqual(m.licensed_charity_identity(org,dict(base),'GA',10),outcome)
            self.assertEqual(m.licensed_charity_identity(org,{**base,'ein':'123456789'},'GA',10),'rejected')

    def test_nm_real_same_label_transitional_period_and_controls(self):
        rows=[(2024,'Registration Submitted 20244022608235332','3/23/2026'),
              (2024,'Registration Submitted 20244022517636260','6/25/2025'),
              (2025,'Tax Year Registration Open','7/1/2026')]
        periods=[{'tax_year':2024,'period_start':'7/1/2024','period_end':'6/30/2025'},
                 {'tax_year':2024,'period_start':'1/1/2024','period_end':'6/30/2024'}]
        pick=lambda r,p:g.nm_submitted_period(r,(2024,'20244022608235332','3/23/2026'),p,d)
        self.assertEqual(pick(rows,periods),'6/30/2025')
        self.assertEqual(pick(rows,periods[:1]),'6/30/2025')
        self.assertEqual(pick(rows,[]),'')
        for history,records in [(rows[:1],periods),
                  (rows,[periods[0],{**periods[1],'period_end':'7/1/2024'}]),
                  ([*rows[:1],(2024,'Registration Submitted 20244022517636260','7/1/2025')],periods),
                  (rows,[periods[0],{**periods[1],'period_start':'7/1/2023'}])]:
            with self.assertRaisesRegex(ValueError,'Conflicting'):
                pick(history,records)

    def test_ms_retry_only_first_incomplete_signed_search(self):
        record={'state':'MS','completed':[],'expires':120,'pending':{'query_id':'signed','query':{'state':'MS','operation':'search','name':'Goodwill Industries International Inc.'}}}
        payload={'query_id':'signed','reason':'NY_CONNECTOR_INCOMPLETE'}
        self.assertEqual(g.ms_recovery_name(record,payload,100),'Goodwill Industries International')
        self.assertEqual(g.ms_recovery_name(record,payload,103),'')
        for change in ({'state':'GA'},{'completed':[{}]},{'ms_search_recovery':'already used'}):
            self.assertEqual(g.ms_recovery_name({**record,**change},payload,100),'')
        for change in ({'query_id':'stale'},{'reason':'NY_CONNECTOR_VERIFICATION_REQUIRED'}):
            self.assertEqual(g.ms_recovery_name(record,{**payload,**change},100),'')

    def test_or_link_is_exact_state_report(self):
        good='/Charities/Charity/GetCharityReport?rptId=1845041673'
        self.assertTrue(g.or_filing_link(good))
        for url in ('https://example.com'+good,good+'&other=1',good+'#x','/Charities/Charity/details?charityID=76393','//justice.oregon.gov:443'+good):
            self.assertFalse(g.or_filing_link(url))

    def test_wv_image_requires_exact_identifier_and_status_and_date(self):
        body='ID: 5218\nInitial Registration Date: 05/03/2006\nOrganization Name: Network For Teaching Entrepreneurship, Inc.\nExpiration Date: 05/03/2027\nStatus: Active'
        args=('5218','Network For Teaching Entrepreneurship, Inc.','05/03/2027','Active')
        self.assertTrue(wv_current_detail_binding(body,*args))
        for old,new in [('5218','52189'),('2027','2020'),('Active','Inactive'),('Network','Other')]:
            self.assertFalse(wv_current_detail_binding(body.replace(old,new),*args))

    def test_ga_grid_unbound_negative_falls_back_to_history(self):
        query={'state':'GA','orgName':'Khan Academy'}
        url='https://verify.sos.ga.gov/verification/SearchResults.aspx'
        text='Search Results\nResults Full Name License # Profession License Type Status Address\n1'
        self.assertFalse(ss.ga_completed_results_snapshot({'state':'GA'},query,{'rows':[]},url,text))
