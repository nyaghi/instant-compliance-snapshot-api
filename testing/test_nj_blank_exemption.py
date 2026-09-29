"""Explicit EIN-linked NJ exemptions without a charity registration number."""
import copy
import unittest
from unittest.mock import Mock
import registry_snapshot_server as m
from testing.capacity_lab import test_nj_public_query as nj_fixture


def exempt_data():
    data = copy.deepcopy(nj_fixture.DATA)
    for attr in data['Records'][0]['Attributes']:
        if attr['Name'] == 'accountnumber': attr['DisplayValue'] = ''
        if attr['Name'] == 'crsm_filestanding': attr['DisplayValue'] = 'Exempt'
    return data


class ExemptionEvidence(unittest.TestCase):
    def test_exact_ein_and_explicit_exemption_allow_blank_registration(self):
        row = m.nj_exact_ein_exempt_row(exempt_data(), '123456789')
        self.assertEqual(row, ('Example Relief', '', '123456789', 'Exempt'))

    def test_other_status_missing_identity_and_conflicts_remain_incomplete(self):
        for field, value in [('name', ''), ('crsm_federalein', '987654321'),
                             ('crsm_federalein', '1234567890'), ('crsm_federalein', None),
                             ('crsm_filestanding', 'Compliant'), ('crsm_filestanding', 'Exempt - Revoked'),
                             ('crsm_filestanding', ''), ('accountnumber', 'CH12345')]:
            with self.subTest(field=field, value=value):
                data = exempt_data()
                next(a for a in data['Records'][0]['Attributes'] if a['Name'] == field)['DisplayValue'] = value
                self.assertIsNone(m.nj_exact_ein_exempt_row(data, '123456789'))

    def test_partial_duplicate_or_error_grid_cannot_establish_exemption(self):
        source = exempt_data()
        variants = [{**source, 'MoreRecords': True}, {**source, 'ItemCount': 2},
                    {**source, 'ItemCount': True}, {**source, 'PageNumber': True},
                    {**source, 'PageNumber': 2}, {**source, 'Error': 'failed'},
                    {**source, 'Success': False}, {**source, 'Records': source['Records'] * 2}]
        duplicate = copy.deepcopy(source)
        duplicate['Records'][0]['Attributes'].append({'Name': 'crsm_federalein', 'DisplayValue': '123456789'})
        variants.append(duplicate)
        for data in variants:
            self.assertIsNone(m.nj_exact_ein_exempt_row(data, '123456789'))
        for query in ['Example Relief', '', '000000000', '12-3456789', None]:
            self.assertIsNone(m.nj_exact_ein_exempt_row(source, query))

    def test_browser_response_is_still_bound_to_the_requested_query(self):
        url = 'https://charportal.dca.njoag.gov/_services/entity-grid-data.json/test-grid'
        request = Mock(url=url, method='POST', post_data_json={'search':'123456789', 'page':1})
        response = request.response.return_value
        response.url=url; response.status=200; response.headers={'content-type':'application/json'}
        response.json.return_value=exempt_data()
        self.assertEqual(m.nj_completed_query_rows(request, '123456789'), [('Example Relief','','123456789','Exempt')])
        self.assertIsNone(m.nj_completed_query_rows(request, '987654321'))
        request.post_data_json['filter']='active only'
        self.assertIsNone(m.nj_completed_query_rows(request, '123456789'))


class PublicExemption(unittest.TestCase):
    # Reuse the ordinary request fixture, but run these focused tests separately
    # from historical whole-file AST comparisons tied to earlier lab releases.
    setUp = nj_fixture.PublicQuery.setUp
    request = nj_fixture.PublicQuery.request
    def test_blank_exemption_uses_same_status_interpreter_without_detail_request(self):
        self.data = exempt_data()
        result, body = m.search_nj_public_details(self.org)
        self.assertEqual(result.status, 'Exempt'); self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, '123456789')
        self.assertEqual(result.matched_registry_name, 'Example Relief')
        self.assertEqual(len(self.calls), 4)
        self.assertNotIn('NJ Registration #', body)
        self.assertTrue(all('/retrieveRegistration/' not in url for _, url, _ in self.calls))

    def test_wrong_ein_or_nonexempt_blank_number_preserves_browser_fallback(self):
        for field, value in [('crsm_federalein','987654321'), ('crsm_filestanding','Compliant')]:
            self.data=exempt_data()
            next(a for a in self.data['Records'][0]['Attributes'] if a['Name']==field)['DisplayValue']=value
            self.assertIsNone(m.search_nj_public_details(self.org))


if __name__ == '__main__': unittest.main()
