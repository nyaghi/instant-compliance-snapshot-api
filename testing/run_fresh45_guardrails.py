"""Reported September 12 retrieval fixes and independent false-positive controls."""
import sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class ReportedCases(unittest.TestCase):
    farrier='American Farrier’s Association Foundation Inc.'
    def org(self,name=None,ein='872999231'):
        return c.checker.Organization(name or self.farrier,ein)
    def test_typographic_apostrophes_keep_ascii_matching_semantics(self):
        for char in ['’','‘','ʼ','＇']:
            for name in [self.farrier,"First Responders Children’s Foundation"]:
                value=name.replace('’',char)
                ascii_name=name.replace('’',"'")
                self.assertEqual(c.normalized_match_name(value),c.normalized_match_name(ascii_name))
                self.assertEqual(c.checker.normalize_name(value),c.checker.normalize_name(ascii_name))
                self.assertEqual(c.organization_name_variants(value),c.organization_name_variants(ascii_name))
    def test_useful_prefix_within_existing_query_budgets(self):
        org=self.org()
        for queries in [c.build_search_queries(org.organization_name,org.ein,include_ein=False,max_queries=8),
                        c.wv_preferred_query_variants(org.organization_name,org.ein)[:4],
                        c.wi_search_names_for_org(org)[:6]]:
            self.assertIn('American Farrier',queries)
        self.assertEqual(c.build_search_queries(org.organization_name,org.ein,include_ein=True,max_queries=8)[0],org.ein)
    def test_single_possessive_does_not_create_broad_one_word_probe(self):
        self.assertEqual(c.possessive_search_phrases('Children’s Foundation'),[])
    def test_aeon_short_original_query_survives_filter(self):
        self.assertEqual(c.wi_search_names_for_org(self.org('Aeon','411558711'))[0],'Aeon')
    def test_exact_legal_name_before_explicit_dba(self):
        for candidate in ['Aeon (dba Aeon Homes)','Aeon doing business as Aeon Homes']:
            self.assertTrue(c.registry_name_is_safe_for_org(candidate,'Aeon','411558711'))
            self.assertTrue(c.registry_name_is_safe_against_targets(candidate,['Aeon'],'Aeon','411558711'))
        for candidate in ['Aeon Homes','Aeon Foundation','Aeon (Minnesota Chapter)','Aeon Housing dba Aeon']:
            self.assertFalse(c.explicit_legal_identity_match('Aeon',candidate))
    def test_unrelated_related_entities_still_fail_matching(self):
        for requested,candidate in [('Air Force Academy Foundation','AIR FORCE ACADEMY ATHLETIC CORPORATION'),
                                    ('National Marrow Donor Program','National Marrow Donor Program Foundation')]:
            self.assertNotEqual(c.score_candidate(requested,'',{'name':candidate})['decision'],'accepted')
    def wi_row(self,name='AMERICAN FARRIERS ASSOCIATION INC',license='23067-800'):
        return f'<tr><td>{license}</td><td>Charitable Organization</td><td><a href="CredSummaryDetails.aspx?chid=945248">{name}</a></td><td>Lexington KY</td><td>7/1/2022</td><td>7/31/2025</td></tr>'
    def test_wi_missing_foundation_is_review_never_a_positive_or_negative(self):
        org=self.org();targets=c.organization_match_target_variants(org.organization_name,org.ein)
        candidate=c.wi_candidate_from_row_html(self.wi_row(),targets,org.organization_name,org.ein)
        self.assertIsNotNone(candidate);self.assertTrue(candidate['identity_conflict']);self.assertEqual(candidate['score'],0)
        with patch.object(c,'wi_http_search_best_match',return_value=(candidate,True)):
            result=c.search_wi(None,org)
        with patch.object(c,'public_profile_for_ein',return_value={}):
            data=c.response_data_for_lookup(result,'',org,org.organization_name,org.ein,'WI',time.perf_counter())
        self.assertEqual(data['status'],'Needs Review');self.assertFalse(data['success'])
        self.assertFalse(data['matched_registry_name']);self.assertIn('23067-800',data['comments'])
        self.assertEqual(data['identity_review_evidence']['registry_name'],'AMERICAN FARRIERS ASSOCIATION INC')
    def test_exact_wi_foundation_beats_related_review(self):
        org=self.org();targets=c.organization_match_target_variants(org.organization_name,org.ein)
        related=c.wi_candidate_from_row_html(self.wi_row(),targets,org.organization_name,org.ein)
        with patch.object(c,'wi_http_detail_status',return_value='License is current (Active)'):
            exact=c.wi_candidate_from_row_html(self.wi_row('AMERICAN FARRIERS ASSOCIATION FOUNDATION INC','88888-800'),targets,org.organization_name,org.ein)
        self.assertTrue(c.wi_better_candidate(exact,related));self.assertFalse(c.wi_better_candidate(related,exact))
    def test_review_does_not_include_unrelated_or_wrong_profession(self):
        for name,license in [('OTHER FARRIERS ASSOCIATION INC','23067-800'),('AMERICAN FARRIERS ASSOCIATION INC','23067-100')]:
            self.assertIsNone(c.wi_foundation_identity_review(name,self.farrier,license,'CredSummaryDetails.aspx?chid=1','7/31/2025'))
    def test_va_exact_identity_survives_unconfirmed_registration(self):
        org=self.org('Al-Ayn Social Care Foundation','47-1614315')
        entity={'id':'74671','name':org.organization_name,'fullName':org.organization_name,'ein':org.ein,'status':'Not Authorized to Solicit'}
        with patch.object(c,'va_evoke_entity_search_by_ein',return_value=[entity]),patch.object(c,'va_evoke_registrations_for_entity',return_value=[]):
            result=c.search_va_evoke_api(org)
        with patch.object(c,'public_profile_for_ein',return_value={}):
            data=c.response_data_for_lookup(result,'',org,org.organization_name,org.ein,'VA',time.perf_counter())
        self.assertEqual(data['status'],'Unable to Confirm');self.assertFalse(data['success'])
        self.assertEqual(data['matched_registry_name'],org.organization_name)
        self.assertIn('Not Authorized to Solicit',data['comments']);self.assertIn('no registration entries',data['comments'])
        self.assertEqual(data['va_entity_evidence']['ein'],'471614315')
    def test_va_mismatched_evidence_cannot_preserve_identity(self):
        org=self.org('Example Foundation','123456789')
        r=c.checker.StateResult(org.organization_name,org.ein,'VA','Unable to Confirm','')
        r.reason_code='VA_MATCHED_BY_EXACT_FEIN';r.matched_registry_name=org.organization_name;r.matched_registry_identifier='1'
        r.va_entity_evidence={'ein':'987654321','name':org.organization_name,'id':'1'}
        c.normalize_registry_match_fields(r,org);self.assertFalse(r.matched_registry_name)

if __name__=='__main__':unittest.main(verbosity=2)
