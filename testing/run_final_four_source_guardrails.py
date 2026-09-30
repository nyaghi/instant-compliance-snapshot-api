"""Observed AL/NC/NV source shapes; no claim of live transport readiness.

Fixtures transcribe public pages inspected on 2026-09-29. Mutated fixtures test
failure boundaries. Organization examples are tests only, never runtime rules.
"""
import copy
from datetime import date
import time
import unittest
from unittest.mock import patch

import registry_snapshot_server as cc


class AsOf(date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 29)


AL_HEADERS = ['Name', 'License/Registration#', 'Status', 'Registration Type',
              'Issued Date', 'Expiration Date', 'Address', 'City', 'State', 'Zip', 'Print']
AL_ROWS = [
    ['YWCA of Birmingham', 'AL97-252', 'Active', 'Charitable Organization', '06/11/2004',
     '03/31/2027', '309 North 23rd Street', 'Birmingham', 'AL', '35203', ''],
    ['YWCA of the USA National Board', 'AL97-431', 'Active', 'Charitable Organization',
     '08/29/2001', '03/28/2027', '1400 I Street NW', 'Washington', 'DC', '20005', ''],
]
NC = {'CSL Legal Name': "America's Charities", 'CSL Type': 'Charitable Organization',
      'Status': 'Current Active – Filing Extension Granted', 'License': 'SL000448',
      'Expiration Date': '5/15/2026', 'Extension End Date': '11/15/2026',
      'profile_url': 'https://www.sosnc.gov/online_services/search/charities_profile/5700751'}
NC_PROFILE = {'Name': "America's Charities", 'Registration #': 'SL000448', 'Status': NC['Status'],
              'Expiration Date': '5/15/2026', 'Extension End Date': '11/15/2026',
              'Last Application Date': '5/13/2026', 'Street': '14200 Park Meadow Dr Ste 330s',
              'City': 'Chantilly', 'State': 'VA', 'Zip': '20151-4210', 'profile_url': NC['profile_url']}
NC_FILINGS = {'url': NC['profile_url'].replace('charities_profile', 'charities_filings'), 'complete': True,
              'rows': [{'type': 'Renewal Charity', 'date': '11/19/2024'},
                       {'type': 'Renewal Charity', 'date': '11/17/2025'},
                       {'type': 'Federal Extension', 'date': '5/13/2026'}]}
NV = {'Entity Name': 'MAKE-A-WISH FOUNDATION OF AMERICA', 'NV Business ID': 'NV20121738342',
      'Entity Status': 'Active', 'Entity Type': 'Foreign Non-Profit Corporation (80)',
      'FEIN': '-', 'Solicits Charitable Contribution?': 'No', 'IRS Registered Name': '-',
      'Campaign Name': '-', 'Formation Date in Nevada': '12/10/2012',
      'Annual Renewal Due Date/Expiration Date': '12/31/2026'}
NV_FILINGS = {'identifier': NV['NV Business ID'], 'name': NV['Entity Name'], 'complete': True, 'total': 2,
              'headers': ['Filed Date', 'Effective Date', 'Filing Number', 'Filing Type', 'Source', 'No. of Pages'],
              'rows': [['10/29/2025', '10/29/2025', '20255271827', 'Annual List', 'Online', '3'],
                       ['11/07/2024', '11/07/2024', '20244455873', 'Annual List', 'Online', '3']]}
# Filing-history fixture shortened with matching count; live NV history has 19.
NV_SOLICITATION = {**NV, 'Entity Name': 'Five Below Foundation', 'NV Business ID': 'NV20222449441',
    'Entity Status': 'Registered', 'Entity Type': 'Foreign Entities Not Required to Register In Nevada',
    'IRS Registered Name': 'Five Below Foundation', 'Formation Date in Nevada': '05/12/2022',
    'Annual Renewal Due Date/Expiration Date': '05/31/2027'}
NV_SOLICITATION_FILINGS = {**NV_FILINGS, 'identifier': NV_SOLICITATION['NV Business ID'],
    'name': NV_SOLICITATION['Entity Name'], 'total': 5,
    'rows': [[d, d, number, 'Charitable Solicitation Registration Statement', source, pages]
             for d, number, source, pages in [
                 ('05/05/2026', '20265733038', 'Email', '2'), ('05/01/2025', '20254868597', 'Mail', '2'),
                 ('05/31/2024', '20244119724', 'Email', '3'), ('05/31/2023', '20233375267', 'Email', '3'),
                 ('05/12/2022', '20222317134', 'Online', '3')]]}
TN = {'Name': 'ROCKY MOUNTAIN ELK FOUNDATION, INC.', 'CO Number': 'CO3674', 'Status': 'Active',
      'Registration Date': '09/13/1999', 'Expiration Date': '11/27/2026',
      'Address': '5705 GRANT CREEK ROAD MISSOULA MT 59808',
      'financial_periods': ['12/31/2024', '12/31/2023'], 'financial_count': 2}
# Financial fixture shortened with a matching count; full public table has 31.
TN_ROW = {'name': TN['Name'], 'identifier': 'CO3674', 'city': 'MISSOULA', 'region': 'MT',
          'aliases': ["RMEF 'CHAPTER NAME'", "ROCKY MOUNTAIN ELK FOUNDATION 'CHAPTER NAME'"]}


class SourceControls(unittest.TestCase):
    def setUp(self):
        fixed = patch.object(cc, 'date', AsOf)
        fixed.start(); self.addCleanup(fixed.stop)

    def al(self, **changes):
        return dict(headers=AL_HEADERS, rows=copy.deepcopy(AL_ROWS), total=2,
                    complete=True, verification_pending=False, **changes)

    def test_nv_nonqualified_entity_requires_actual_charity_statement_history(self):
        row = cc.nv_charity_detail_evidence(NV_SOLICITATION, NV_SOLICITATION['NV Business ID'])
        self.assertEqual(row['status'], 'Unable to Confirm')
        confirmed = cc.nv_charity_filings_evidence(row, NV_SOLICITATION_FILINGS)
        self.assertEqual(confirmed['status'], 'Current')
        self.assertEqual(confirmed['solicitation_statement_filed'], date(2026,5,5))
        self.assertEqual(confirmed['initial'], date(2022,5,12))
        for changes in [{'complete':False}, {'total':6}, {'name':'Different Charity'},
                        {'identifier':'NV000000000'}, {'rows':[], 'total':0}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(row, {**NV_SOLICITATION_FILINGS, **changes})

    def test_nv_other_filing_types_cannot_establish_charity_scope(self):
        row = cc.nv_charity_detail_evidence(NV_SOLICITATION, NV_SOLICITATION['NV Business ID'])
        for kind in ['Annual List', 'Foreign Qualification', 'Declaration of Exemption', 'Unknown']:
            history=copy.deepcopy(NV_SOLICITATION_FILINGS)
            for cells in history['rows']: cells[3]=kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(row, history)

    def test_nv_solicitation_status_and_expiration_keep_adverse_precedence(self):
        for raw, due, expected in [('Registered','05/31/2026','Delinquent'),
                                  ('Registered','12/31/2026','Upcoming Filing'),
                                  ('Default','05/31/2027','Delinquent'),
                                  ('Revoked','05/31/2027','Revoked'),
                                  ('Suspended','05/31/2027','Suspended'),
                                  ('Withdrawn','05/31/2027','Closed / Withdrawn / Canceled')]:
            fields={**NV_SOLICITATION,'Entity Status':raw,'Annual Renewal Due Date/Expiration Date':due}
            row=cc.nv_charity_detail_evidence(fields,fields['NV Business ID'])
            with self.subTest(raw=raw,due=due):
                self.assertEqual(cc.nv_charity_filings_evidence(row,NV_SOLICITATION_FILINGS)['status'],expected)

    def test_nv_solicitation_missing_deadline_and_future_filing_remain_unconfirmed(self):
        fields={**NV_SOLICITATION,'Annual Renewal Due Date/Expiration Date':'-'}
        row=cc.nv_charity_detail_evidence(fields,fields['NV Business ID'])
        with self.assertRaises(ValueError): cc.nv_charity_filings_evidence(row,NV_SOLICITATION_FILINGS)
        row=cc.nv_charity_detail_evidence(NV_SOLICITATION,NV_SOLICITATION['NV Business ID'])
        history=copy.deepcopy(NV_SOLICITATION_FILINGS);history['rows'][0][0]='05/05/2099'
        with self.assertRaises(ValueError): cc.nv_charity_filings_evidence(row,history)

    def test_al_both_candidates_preserved_for_master_selection(self):
        records = cc.al_charity_search_evidence(self.al())
        self.assertEqual([r['identifier'] for r in records], ['AL97-252', 'AL97-431'])
        self.assertEqual(records[1]['status'], 'Upcoming Filing')
        self.assertEqual(records[1]['source_issued'], date(2001, 8, 29))
        self.assertIsNone(records[1]['initial'])
        self.assertEqual(records[1]['location'], 'Washington, DC')

    def test_al_only_complete_search_can_be_empty(self):
        payload = self.al(); payload.update(rows=[], total=0)
        self.assertEqual(cc.al_charity_search_evidence(payload), [])
        for bad in [{'complete': False}, {'verification_pending': True},
                    {'total': 1}, {'total': False}, {'headers': AL_HEADERS[:-1]}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.al_charity_search_evidence({**payload, **bad})

    def test_al_partial_and_duplicate_pages_rejected(self):
        for bad in [{'rows': AL_ROWS[:1]}, {'rows': [AL_ROWS[0], AL_ROWS[0]]}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.al_charity_search_evidence({**self.al(), **bad})

    def test_al_non_charity_credentials_do_not_prove_registration(self):
        payload = self.al()
        for r in payload['rows']: r[3] = 'Professional Fundraiser'
        self.assertEqual(cc.al_charity_search_evidence(payload), [])

    def test_al_adverse_status_survives_future_expiration(self):
        for raw, expected in [('Revoked', 'Revoked'), ('Suspended', 'Suspended'),
                              ('Inactive', 'Closed / Withdrawn / Canceled')]:
            payload = self.al(); payload['rows'][0][2] = raw
            self.assertEqual(cc.al_charity_search_evidence(payload)[0]['status'], expected)

    def test_al_explicit_active_exempt_category(self):
        payload = self.al(); payload['rows'][0][3] = 'Exempted Charity'
        self.assertEqual(cc.al_charity_search_evidence(payload)[0]['status'], 'Exempt')

    def test_al_malformed_date_not_silently_missing(self):
        payload = self.al(); payload['rows'][0][5] = 'not loaded'
        with self.assertRaises(ValueError): cc.al_charity_search_evidence(payload)

    def test_nc_extension_precedes_expired_base(self):
        r = cc.nc_charity_record_evidence(NC)
        self.assertEqual(r['status'], 'Upcoming Filing')
        self.assertEqual(r['expiration'], date(2026, 11, 15))
        self.assertEqual(r['base_expiration'], date(2026, 5, 15))
        self.assertIsNone(r['renewal'])

    def test_nc_registry_aliases_survive_card_and_profile_binding(self):
        fields = {**NC, 'display_name': 'Current Charity DBA',
                  'aliases': [NC['CSL Legal Name'], 'Former Legal Charity Name']}
        card = cc.nc_charity_record_evidence(fields)
        self.assertEqual(card['name'], 'Current Charity DBA')
        self.assertIn(NC['CSL Legal Name'], card['aliases'])
        result = cc.nc_charity_profile_evidence(card, NC_PROFILE)
        self.assertEqual(result['name'], NC_PROFILE['Name'])
        self.assertIn('Current Charity DBA', result['aliases'])
        self.assertIn('Former Legal Charity Name', result['aliases'])
        for bad in [{'Name': 'Unrelated Organization'}, {'Registration #': 'SL999999'},
                    {'profile_url': NC_PROFILE['profile_url']+'1'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.nc_charity_profile_evidence(card, {**NC_PROFILE, **bad})

    def test_nc_source_aliases_require_bounded_named_evidence(self):
        for bad in [{'aliases': 'not a list'}, {'aliases': ['']}, {'aliases': [None]},
                    {'aliases': ['x'*501]}, {'aliases': ['A']*33},
                    {'display_name': 'Unbound displayed name', 'aliases': []}, {'display_name': None}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.nc_charity_record_evidence({**NC, **bad})

    def test_nc_alias_payload_remains_query_bound(self):
        query = {'state': 'NC', 'operation': 'search', 'name': 'Current Charity DBA'}
        fields = {**NC, 'display_name': 'Current Charity DBA', 'aliases': [NC['CSL Legal Name']]}
        payload = {'state': 'NC', 'query': query, 'complete': True, 'verification_pending': False,
                   'total': 1, 'rows': [fields]}
        cleaned = cc.final_four_clean_evidence(payload, query)
        self.assertEqual(cleaned['rows'][0]['aliases'], [NC['CSL Legal Name']])
        with self.assertRaises(ValueError):
            cc.final_four_clean_evidence(payload, {**query, 'name': 'Other Name'})

    def test_nc_explicit_exemption_without_expiration_is_complete(self):
        fields = {**NC, 'CSL Legal Name': 'YWCA of the U.S.A.', 'CSL Type': 'CSL Exempt Organization',
                  'License': 'EX003050', 'Status': 'CSL Exempt', 'Expiration Date': '', 'Extension End Date': '',
                  'profile_url': 'https://www.sosnc.gov/online_services/search/charities_profile/9819989'}
        row = cc.nc_charity_record_evidence(fields)
        self.assertEqual(row['status'], 'Exempt')
        self.assertIsNone(row['expiration'])
        self.assertEqual(cc.nc_charity_record_evidence({**fields, 'Status': 'Revoked'})['status'], 'Revoked')
        self.assertEqual(cc.nc_charity_record_evidence({**fields, 'Status': 'Unrecognized'})['status'], 'Unable to Confirm')
        for invalid in [{'License': 'PF003050'}, {'CSL Type': 'Professional Fundraiser'}]:
            with self.assertRaises(ValueError): cc.nc_charity_record_evidence({**fields, **invalid})

    def test_nc_license_prefix_does_not_override_explicit_record_category(self):
        # Public RMHC search: EX011792 is labeled Charitable Organization;
        # public Junior search: SL007110 is labeled CSL Exempt Organization.
        for identifier, kind, raw, expected in [
                ('EX011792', 'Charitable Organization', 'Withdrawn', 'Closed / Withdrawn / Canceled'),
                ('SL007110', 'CSL Exempt Organization', 'CSL Exempt', 'Exempt')]:
            with self.subTest(identifier=identifier):
                row = cc.nc_charity_record_evidence({**NC, 'License': identifier,
                    'CSL Type': kind, 'Status': raw, 'Expiration Date': '', 'Extension End Date': ''})
                self.assertEqual(row['identifier'], identifier)
                self.assertEqual(row['status'], expected)
        for identifier in ['', 'PF007110', 'SL', 'EX123/SL456']:
            with self.assertRaises(ValueError):
                cc.nc_charity_record_evidence({**NC, 'License': identifier})

    def test_nc_unissued_application_requires_explicit_source_category_and_status(self):
        fields = {**NC, 'License': '', 'CSL Type': 'In-Process', 'Status': 'In-Process',
                  'Expiration Date': '', 'Extension End Date': ''}
        row = cc.nc_charity_record_evidence(fields)
        self.assertTrue(row['unissued_application'])
        self.assertEqual(row['status'], 'Needs Review')
        for bad in [{'Status': 'Active'}, {'CSL Type': 'Charitable Organization'},
                    {'Expiration Date': '12/31/2027'}, {'profile_url': 'https://example.com/profile/1'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.nc_charity_record_evidence({**fields, **bad})

    def test_nc_extension_does_not_require_special_status_wording(self):
        for raw in ['Active', 'Current', 'Current Active']:
            self.assertEqual(cc.nc_charity_record_evidence({**NC, 'Status': raw})['status'], 'Upcoming Filing')

    def test_nc_no_extension_uses_original_expiration(self):
        r = cc.nc_charity_record_evidence({**NC, 'Status': 'Current Active', 'Extension End Date': ''})
        self.assertEqual(r['status'], 'Delinquent')
        self.assertEqual(r['expiration'], date(2026, 5, 15))

    def test_nc_expired_extension_is_not_current(self):
        self.assertEqual(cc.nc_charity_record_evidence({**NC, 'Extension End Date': '8/15/2026'})['status'], 'Delinquent')

    def test_nc_adverse_status_precedes_future_extension(self):
        for raw, expected in [('Revoked', 'Revoked'), ('Suspended', 'Suspended'),
                              ('Canceled', 'Closed / Withdrawn / Canceled')]:
            r = cc.nc_charity_record_evidence({**NC, 'Status': raw})
            self.assertEqual(r['status'], expected)
            self.assertEqual(r['expiration'], date(2026, 11, 15))

    def test_nc_extension_missing_or_malformed_is_not_negative(self):
        for value in ['', '-', 'Loading', '2/31/2026']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                cc.nc_charity_record_evidence({**NC, 'Extension End Date': value})

    def test_nc_unrecognized_status_is_not_inferred_from_date(self):
        self.assertEqual(cc.nc_charity_record_evidence({**NC, 'Status': 'Unrecognized'})['status'], 'Unable to Confirm')

    def test_nc_profile_is_bound_to_official_charity_source(self):
        for url in ['https://example.test/online_services/search/charities_profile/5700751',
                    'https://www.sosnc.gov/online_services/search/business_profile/5700751']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                cc.nc_charity_record_evidence({**NC, 'profile_url': url})

    def test_nc_comment_and_deadline_explain_actual_extension(self):
        org = cc.checker.Organization("America's Charities", '54-1517707')
        row = cc.nc_charity_record_evidence(NC)
        with patch.object(cc, 'select_licensed_charity', return_value=(row, '')):
            result = cc.final_four_license_result(org, 'NC', [row], time.monotonic()+10, row['url'])
        self.assertEqual(result.computed_due_date, '2026-11-15')
        self.assertIn('extension end date of 2026-11-15', result.source_note)
        self.assertIn('original expiration date was 2026-05-15', result.source_note)
        self.assertNotIn('license expiration date is 2026-11-15', result.source_note)

    def test_nc_last_application_extension_not_mislabeled_renewal(self):
        r = cc.nc_charity_profile_evidence(cc.nc_charity_record_evidence(NC), NC_PROFILE, NC_FILINGS)
        self.assertEqual(r['source_last_application'], date(2026, 5, 13))
        self.assertEqual(r['renewal'], date(2025, 11, 17))
        self.assertEqual(r['expiration'], date(2026, 11, 15))
        self.assertEqual(r['location'], 'Chantilly, VA')
        self.assertIsNone(r['initial'])

    def test_nc_without_history_renewal_remains_blank(self):
        r = cc.nc_charity_profile_evidence(cc.nc_charity_record_evidence(NC), NC_PROFILE)
        self.assertIsNone(r['renewal'])

    def test_nc_wrong_profile_or_history_never_attached(self):
        card = cc.nc_charity_record_evidence(NC)
        for bad in [{'Registration #': 'SL999999'}, {'Name': 'Local Chapter'}, {'profile_url': NC['profile_url']+'9'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.nc_charity_profile_evidence(card, {**NC_PROFILE, **bad})
        for bad in [{'url': NC_FILINGS['url']+'9'}, {'complete': False}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                cc.nc_charity_profile_evidence(card, NC_PROFILE, {**NC_FILINGS, **bad})

    def test_nv_matched_nonprofit_uses_displayed_annual_due(self):
        r = cc.nv_charity_detail_evidence(NV, 'NV20121738342')
        self.assertEqual(r['status'], 'Upcoming Filing')
        self.assertEqual(r['expiration'], date(2026, 12, 31)); self.assertIsNone(r['initial'])
        self.assertIsNone(r['renewal'])
        self.assertEqual(r['entity_expiration'], date(2026, 12, 31))

    def test_nv_separate_solicitation_flag_does_not_replace_entity_rule(self):
        r = cc.nv_charity_detail_evidence({**NV, 'Solicits Charitable Contribution?': 'Yes'}, 'NV20121738342')
        self.assertEqual(r['status'], 'Upcoming Filing')
        self.assertTrue(r['solicitation_declared'])

    def test_nv_registered_agent_and_other_entity_types_not_accepted(self):
        for entity in ['Commercial Registered Agent', 'NT7 Business License - Other', 'Domestic Corporation (78)']:
            with self.subTest(entity=entity), self.assertRaises(ValueError):
                cc.nv_charity_detail_evidence({**NV, 'Entity Type': entity}, 'NV20121738342')

    def test_nv_adverse_status_precedes_future_date(self):
        for raw, expected in [('Permanently Revoked', 'Revoked'), ('Default', 'Delinquent'),
                              ('Dissolved', 'Closed / Withdrawn / Canceled')]:
            r = cc.nv_charity_detail_evidence({**NV, 'Entity Status': raw}, 'NV20121738342')
            self.assertEqual(r['status'], expected)

    def test_nv_agent_address_never_becomes_organization_address(self):
        r = cc.nv_charity_detail_evidence({**NV, 'Agent Street Address': '187 E WARM SPRINGS ROAD, LAS VEGAS, NV'}, 'NV20121738342')
        self.assertEqual(r['street'], ''); self.assertEqual(r['location'], '')

    def test_nv_comment_identifies_basis_and_preserves_separate_flag(self):
        org = cc.checker.Organization('Make-A-Wish Foundation of America', '86-0481941')
        row = cc.nv_charity_detail_evidence(NV, 'NV20121738342')
        with patch.object(cc, 'select_licensed_charity', return_value=(row, '')):
            result = cc.final_four_license_result(org, 'NV', [row], time.monotonic()+10, 'https://orion.nv.gov/portal/public/')
        self.assertEqual(result.computed_due_date, '2026-12-31')
        self.assertIn('Annual Renewal Due Date/Expiration Date', result.source_note)
        self.assertIn('nonprofit corporation', result.source_note)
        self.assertIn('field displays No', result.source_note)

    def test_nv_wrong_business_id_rejected(self):
        with self.assertRaises(ValueError): cc.nv_charity_detail_evidence(NV, 'NV19931054903')

    def test_nv_missing_fields_or_malformed_fein_rejected(self):
        for field in NV:
            incomplete = dict(NV); incomplete.pop(field)
            with self.subTest(field=field), self.assertRaises(ValueError):
                cc.nv_charity_detail_evidence(incomplete, 'NV20121738342')
        with self.assertRaises(ValueError):
            cc.nv_charity_detail_evidence({**NV, 'FEIN': 'unknown'}, 'NV20121738342')

    def test_tn_expiration_and_latest_filing_are_separate(self):
        r = cc.tn_charity_detail_evidence(TN, 'CO3674', TN_ROW)
        self.assertEqual(r['status'], 'Upcoming Filing')
        self.assertEqual(r['expiration'], date(2026, 11, 27))
        self.assertEqual(r['initial'], date(1999, 9, 13))
        self.assertEqual(r['latest_filed_period'], date(2024, 12, 31))
        self.assertIsNone(r['renewal'])
        self.assertEqual(r['street'], '5705 GRANT CREEK ROAD')
        self.assertEqual(r['location'], 'MISSOULA, MT')

    def test_tn_templates_are_not_alternate_names(self):
        r = cc.tn_charity_detail_evidence(TN, 'CO3674', {**TN_ROW, 'aliases': [*TN_ROW['aliases'], 'RMEF']})
        self.assertEqual(r['aliases'], ['RMEF'])

    def test_tn_unsorted_periods_use_latest(self):
        r = cc.tn_charity_detail_evidence({**TN, 'financial_periods': list(reversed(TN['financial_periods']))}, 'CO3674', TN_ROW)
        self.assertEqual(r['latest_filed_period'], date(2024, 12, 31))

    def test_tn_optional_history_not_loaded_does_not_invent_period(self):
        fields = dict(TN); fields.pop('financial_periods'); fields.pop('financial_count')
        r = cc.tn_charity_detail_evidence(fields, 'CO3674', TN_ROW)
        self.assertEqual(r['status'], 'Upcoming Filing')
        self.assertIsNone(r['latest_filed_period'])

    def test_tn_partial_history_not_accepted_as_complete(self):
        with self.assertRaises(ValueError):
            cc.tn_charity_detail_evidence({**TN, 'financial_count': 31}, 'CO3674', TN_ROW)

    def test_tn_detail_binding_and_location_conflict(self):
        cases = [({**TN, 'CO Number': 'CO9999'}, TN_ROW),
                 ({**TN, 'Name': 'ROCKY MOUNTAIN ELK FOUNDATION LOCAL CHAPTER'}, TN_ROW),
                 (TN, {**TN_ROW, 'city': 'NEW YORK', 'region': 'NY'})]
        for fields, row in cases:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                cc.tn_charity_detail_evidence(fields, 'CO3674', row)

    def test_tn_adverse_status_precedes_recent_dates(self):
        self.assertEqual(cc.tn_charity_detail_evidence({**TN, 'Status': 'Revoked'}, 'CO3674', TN_ROW)['status'], 'Revoked')


class MasterIdentityControls(unittest.TestCase):
    def setUp(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset, token)
        for attribute, value in [('date', AsOf),
                                 ('reconciled_registry_address', {'decision': 'not_available'}),
                                 ('licensed_charity_street_evidence', None)]:
            p = patch.object(cc, attribute, value) if attribute == 'date' else patch.object(cc, attribute, return_value=value)
            p.start(); self.addCleanup(p.stop)

    def test_national_record_does_not_select_local_chapter(self):
        org = cc.checker.Organization('YWCA of the USA National Board', '13-1624103')
        rows = cc.al_charity_search_evidence(dict(headers=AL_HEADERS, rows=AL_ROWS, total=2, complete=True, verification_pending=False))
        chosen, review = cc.select_licensed_charity(org, rows, 'AL', time.monotonic()+10)
        self.assertFalse(review)
        self.assertEqual(chosen['identifier'], 'AL97-431')

    def test_confirmed_alias_uses_same_master_identity(self):
        org = cc.checker.Organization('YWCA USA, Inc.', '13-1624103')
        rows = cc.al_charity_search_evidence(dict(headers=AL_HEADERS, rows=AL_ROWS, total=2, complete=True, verification_pending=False))
        cc.REVIEWED_NAME_CONTEXT.set({'131624103': ['YWCA of the USA National Board']})
        chosen, review = cc.select_licensed_charity(org, rows, 'AL', time.monotonic()+10)
        self.assertFalse(review)
        self.assertEqual(chosen['identifier'], 'AL97-431')

    def test_wrong_ein_rejected_in_all_four_new_states(self):
        org = cc.checker.Organization('Make-A-Wish Foundation of America', '86-0481941')
        for state in ['AL', 'NC', 'NV', 'TN']:
            row = cc.nv_charity_detail_evidence({**NV, 'FEIN': '13-1624103'}, 'NV20121738342')
            self.assertEqual(cc.licensed_charity_identity(org, row, state, time.monotonic()+10), 'rejected')

    def test_address_conflict_retains_review_in_all_four_states(self):
        org = cc.checker.Organization('Make-A-Wish Foundation of America', '86-0481941')
        for state in ['AL', 'NC', 'NV', 'TN']:
            row = cc.nv_charity_detail_evidence(NV, 'NV20121738342')
            row['location'] = 'New York, NY'
            with patch.object(cc, 'reconciled_registry_address', return_value={'decision': 'conflict', 'ein_linked_location': 'Phoenix, AZ'}):
                chosen, review = cc.select_licensed_charity(org, [row], state, time.monotonic()+10)
            self.assertIsNone(chosen); self.assertIn('address conflict', review)

    def test_newer_active_same_nonprofit_supersedes_old_revoked_record(self):
        org = cc.checker.Organization('Make-A-Wish Foundation of America', '86-0481941')
        active = cc.nv_charity_detail_evidence(NV, 'NV20121738342')
        old = {**active, 'identifier': 'NV19931054903', 'raw_status': 'Permanently Revoked', 'status': 'Revoked', 'expiration': date(2012, 1, 1)}
        chosen, review = cc.select_licensed_charity(org, [old, active], 'NV', time.monotonic()+10)
        self.assertFalse(review); self.assertEqual(chosen['identifier'], active['identifier'])

    def test_conflicting_equally_current_records_require_review(self):
        org = cc.checker.Organization('Make-A-Wish Foundation of America', '86-0481941')
        active = cc.nv_charity_detail_evidence(NV, 'NV20121738342')
        revoked = {**active, 'identifier': 'NV99999999', 'raw_status': 'Revoked', 'status': 'Revoked'}
        chosen, review = cc.select_licensed_charity(org, [active, revoked], 'NV', time.monotonic()+10)
        self.assertIsNone(chosen); self.assertIn('conflicting statuses', review)

    def test_reviewed_names_precede_generated_queries(self):
        org = cc.checker.Organization('Wild Ones — Natural Landscapers', '39-1695443')
        aliases = ['Wild Ones Natural Landscapers, Ltd.', 'WILD ONES']
        cc.REVIEWED_NAME_CONTEXT.set({'391695443': aliases})
        required, generated = cc.licensed_charity_names(org)
        self.assertEqual(required[1:], aliases)
        self.assertTrue(generated)
        self.assertLessEqual(len(generated), 3 * len(required))


class LookupControls(unittest.TestCase):
    def setUp(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset, token)
        for attr, value in [('date', AsOf), ('reconciled_registry_address', {'decision': 'not_available'})]:
            p = patch.object(cc, attr, value) if attr == 'date' else patch.object(cc, attr, return_value=value)
            p.start(); self.addCleanup(p.stop)
        self.nvrow = {'name': NV['Entity Name'], 'identifier': NV['NV Business ID'], 'entity_type': NV['Entity Type']}
        self.nvurl = 'https://orion.nv.gov/portal/public/#/public/nvsos/en/CaseXscreen?screen=Manage-Business&id=d1b62c76-d5af-4ff3-b07d-038b7fa8d854'
        self.orgs = {'AL': cc.checker.Organization('YWCA of the USA National Board', '13-1624103'),
                     'NC': cc.checker.Organization("America's Charities", '54-1517707'),
                     'NV': cc.checker.Organization(NV['Entity Name'], '86-0481941'),
                     'TN': cc.checker.Organization(TN['Name'], '81-0421425')}
        self.calls = []

    def provider(self, query):
        self.calls.append(query)
        state = query['state']
        if query['operation'] == 'search':
            rows = {'AL': AL_ROWS, 'NC': [NC], 'NV': [self.nvrow], 'TN': [TN_ROW]}[state]
            return {'state': state, 'query': query, 'complete': True, 'verification_pending': False,
                    'rows': copy.deepcopy(rows), 'total': len(rows), 'headers': AL_HEADERS}
        fields = {'NC': NC_PROFILE, 'NV': NV, 'TN': TN}[state]
        payload = {'query': query, 'complete': True, 'fields': copy.deepcopy(fields)}
        if state == 'NC': payload['filings'] = copy.deepcopy(NC_FILINGS)
        if state == 'NV': payload['source_url'] = self.nvurl
        return payload

    def test_full_master_lookup_selects_expected_record_in_all_four(self):
        expected = {'AL': 'AL97-431', 'NC': 'SL000448', 'NV': 'NV20121738342', 'TN': 'CO3674'}
        for state, org in self.orgs.items():
            with self.subTest(state=state):
                result = cc.final_four_browser_lookup(org, state, self.provider)
                self.assertTrue(result.success)
                self.assertEqual(result.matched_registry_identifier, expected[state])
                self.assertIn(result.status, ['Current', 'Upcoming Filing'])

    def test_status_and_comment_rendering_preserve_selected_record_evidence(self):
        for state, org in self.orgs.items():
            with self.subTest(state=state):
                result = cc.final_four_browser_lookup(org, state, self.provider)
                unrelated_body = 'Registered agent: Active. Former entity: Revoked. Expired 12/31/1999.'
                self.assertEqual(cc.true_status_from_body(result, unrelated_body), cc.public_status(result))
                self.assertEqual(cc.comments_for_result_base(result, unrelated_body, cc.public_status(result)), result.source_note)

    def test_complete_primary_positive_does_not_require_a_later_broken_alias(self):
        cc.REVIEWED_NAME_CONTEXT.set({'131624103': ['YWCA USA, Inc.']})
        def primary_only(q):
            if q.get('name') == 'YWCA USA, Inc.':
                raise ValueError('Later alias verification/pagination failed')
            return self.provider(q)
        result = cc.final_four_browser_lookup(self.orgs['AL'], 'AL', primary_only)
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, 'AL97-431')
        self.assertEqual([q['name'] for q in self.calls], ['YWCA of the USA National Board'])

    def test_primary_positive_requires_complete_search_and_detail_before_stopping(self):
        for state in ['NC', 'NV', 'TN']:
            self.calls.clear()
            org = self.orgs[state]
            # This control exercises a distinctive legal name. America's
            # Charities has one distinctive token and remains a short-name
            # control that must exhaust the reviewed aliases.
            if state == 'NC':
                org = cc.checker.Organization('Environmental Law Institute', '52-0901863')
            cc.REVIEWED_NAME_CONTEXT.set({cc.canonical_ein_digits(org.ein): ['Unneeded Alias']})
            def primary_only(q):
                if q.get('name') == 'Unneeded Alias': raise ValueError('Alias incomplete')
                data = self.provider(q)
                if state == 'NC':
                    if q['operation'] == 'search': data['rows'][0]['CSL Legal Name'] = org.organization_name
                    else: data['fields']['Name'] = org.organization_name
                return data
            result = cc.final_four_browser_lookup(org, state, primary_only)
            self.assertTrue(result.success, state)
            self.assertEqual([q['operation'] for q in self.calls], ['search', 'detail'])

    def test_alias_only_positive_still_checks_all_reviewed_names(self):
        org = cc.checker.Organization('National Example Charity', '13-1624103')
        names = ['YWCA of the USA National Board', 'YWCA USA, Inc.']
        cc.REVIEWED_NAME_CONTEXT.set({'131624103': names})
        cc.final_four_browser_lookup(org, 'AL', self.provider)
        self.assertEqual([q['name'] for q in self.calls], [org.organization_name, *names])

    def test_short_primary_positive_still_checks_reviewed_names(self):
        org = cc.checker.Organization('Aeon', '41-1558711')
        cc.REVIEWED_NAME_CONTEXT.set({'411558711': ['Aeon Foundation']})
        def short(q):
            data = self.provider(q)
            data['rows'] = [copy.deepcopy(AL_ROWS[1])]
            data['rows'][0][0] = 'Aeon'; data['total'] = 1
            return data
        cc.final_four_browser_lookup(org, 'AL', short)
        self.assertEqual([q['name'] for q in self.calls], ['Aeon', 'Aeon Foundation'])

    def test_closed_primary_still_searches_for_current_former_name(self):
        org = self.orgs['AL']
        cc.REVIEWED_NAME_CONTEXT.set({'131624103': ['YWCA USA, Inc.']})
        def old_and_current(q):
            data = self.provider(q); data['rows'] = [copy.deepcopy(AL_ROWS[1])]; data['total'] = 1
            if q['name'] == org.organization_name:
                data['rows'][0][2] = 'Inactive'
            else:
                data['rows'][0][0] = 'YWCA USA, Inc.'; data['rows'][0][1] = 'AL97-999'
            return data
        result = cc.final_four_browser_lookup(org, 'AL', old_and_current)
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier, 'AL97-999')
        self.assertEqual(len(self.calls), 2)

    def test_incomplete_second_candidate_cannot_be_hidden_by_primary_positive(self):
        cc.REVIEWED_NAME_CONTEXT.set({'860481941': ['Make A Wish']})
        def incomplete(q):
            data = self.provider(q)
            if q['operation'] == 'search':
                data['rows'].append({**self.nvrow, 'identifier':'NV99999999'}); data['total'] = 2
            elif q['identifier'] == 'NV99999999':
                data['complete'] = False
            return data
        with self.assertRaises(ValueError):
            cc.final_four_browser_lookup(self.orgs['NV'], 'NV', incomplete)

    def test_conflicting_adverse_candidate_prevents_early_positive(self):
        cc.REVIEWED_NAME_CONTEXT.set({'860481941': ['Make A Wish']})
        def conflicting(q):
            data = self.provider(q)
            if q['operation'] == 'search':
                data['rows'].append({**self.nvrow, 'identifier':'NV99999999'}); data['total'] = 2
            elif q['identifier'] == 'NV99999999':
                data['fields'].update({'NV Business ID':'NV99999999','Entity Status':'Revoked'})
            return data
        result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', conflicting)
        self.assertFalse(result.success)
        self.assertEqual(result.status, 'Needs Review')
        self.assertIn('Make A Wish', [q.get('name') for q in self.calls])

    def test_matching_unissued_application_prevents_early_exit(self):
        org = self.orgs['NC']
        cc.REVIEWED_NAME_CONTEXT.set({cc.canonical_ein_digits(org.ein): ['Other Reviewed Name']})
        def unissued(q):
            data = self.provider(q)
            if q['operation'] == 'search':
                data['rows'].append({**NC,'License':'','Status':'In-Process','CSL Type':'In-Process',
                                     'Expiration Date':'','Extension End Date':''}); data['total'] = 2
            return data
        cc.final_four_browser_lookup(org, 'NC', unissued)
        self.assertIn('Other Reviewed Name', [q.get('name') for q in self.calls])

    def test_completed_empty_search_uses_all_bounded_variants(self):
        for state, org in self.orgs.items():
            calls = []
            def empty(query):
                calls.append(query)
                return {**self.provider(query), 'rows': [], 'total': 0}
            result = cc.final_four_browser_lookup(org, state, empty)
            self.assertEqual(result.status, 'Not Registered', state)
            required, generated = cc.licensed_charity_names(org)
            self.assertEqual([q['name'] for q in calls], required + generated)

    def test_tn_completed_directory_does_not_infer_statutory_exemption(self):
        result = cc.final_four_browser_lookup(self.orgs['TN'], 'TN', lambda q: {**self.provider(q), 'rows': [], 'total': 0})
        self.assertEqual(result.status, 'Not Registered')
        self.assertIn('does not determine whether an exemption applies', result.source_note)

    def test_loading_verification_and_incomplete_pagination_cannot_be_negative(self):
        for state, org in self.orgs.items():
            for bad in [{'complete': False}, {'verification_pending': True}, {'total': 25}, {'query': {}}]:
                with self.subTest(state=state, bad=bad), self.assertRaises(ValueError):
                    cc.final_four_browser_lookup(org, state, lambda q: {**self.provider(q), **bad})

    def test_replayed_detail_from_another_query_is_rejected(self):
        for state in ['NC', 'NV', 'TN']:
            def changed(q):
                payload = self.provider(q)
                if q['operation'] == 'detail': payload['query'] = {**q, 'identifier': 'OTHER'}
                return payload
            with self.assertRaises(ValueError): cc.final_four_browser_lookup(self.orgs[state], state, changed)

    def test_nv_unsupported_entity_needs_review_without_opening_detail(self):
        self.nvrow['entity_type'] = 'Registered Agent'
        result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', self.provider)
        self.assertEqual(result.status, 'Unable to Confirm')
        self.assertTrue(all(q['operation'] == 'search' for q in self.calls))

    def test_nv_nr_identity_is_filtered_without_inventing_a_corporation(self):
        for name, expected in [(self.nvrow['name'], 'Unable to Confirm'), ('The Junior Swim League LLC', 'Not Registered')]:
            def nr(query):
                self.assertEqual(query['operation'], 'search')
                row = {'name':name, 'identifier':'NR20230725-22746', 'entity_type':'', 'raw_status':'Expired'}
                return {'state':'NV', 'query':query, 'complete':True, 'verification_pending':False, 'total':1, 'rows':[row]}
            result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', nr)
            self.assertEqual(result.status, expected)
            self.assertFalse(result.matched_registry_identifier)

    def test_nc_unrelated_unissued_application_does_not_block_a_completed_negative(self):
        for name, expected in [("America's Charities", 'Needs Review'), ('Unrelated Junior League', 'Not Registered')]:
            def pending(q):
                self.assertEqual(q['operation'], 'search')
                row = {**NC, 'CSL Legal Name': name, 'License': '', 'CSL Type': 'In-Process',
                       'Status': 'In-Process', 'Expiration Date': '', 'Extension End Date': ''}
                return {'state':'NC', 'query':q, 'complete':True, 'verification_pending':False, 'total':1, 'rows':[row]}
            result = cc.final_four_browser_lookup(self.orgs['NC'], 'NC', pending)
            self.assertEqual(result.status, expected)
            self.assertFalse(result.matched_registry_identifier)

    def test_nv_blank_business_id_is_filtered_but_never_opened_or_classified(self):
        for name, expected in [(self.nvrow['name'], 'Unable to Confirm'), ('Unrelated Regional Charity', 'Not Registered')]:
            def pending(q):
                self.assertEqual(q['operation'], 'search')
                row = {'name':name, 'identifier':'E38494562024-0', 'entity_number':'E38494562024-0',
                       'business_identifier_missing':True, 'entity_type':'Foreign Entities Not Required to Register In Nevada',
                       'raw_status':'Expired'}
                return cc.final_four_clean_evidence({'state':'NV', 'query':q, 'complete':True,
                    'verification_pending':False, 'total':1, 'rows':[row]}, q)
            result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', pending)
            self.assertEqual(result.status, expected)
            self.assertFalse(result.matched_registry_identifier)
            if expected == 'Unable to Confirm':
                self.assertIn('blank NV Business ID', result.source_note)

    def test_nv_blank_business_id_contract_cannot_accept_invented_or_duplicate_identity(self):
        q={'state':'NV','operation':'search','name':self.nvrow['name']}
        row={'name':self.nvrow['name'],'identifier':'E38494562024-0','entity_number':'E38494562024-0',
             'business_identifier_missing':True,'entity_type':'Foreign Entities Not Required to Register In Nevada','raw_status':'Expired'}
        for changes in [{'business_identifier_missing':False},{'entity_number':'E00000002024-0'},
                        {'identifier':'NV123'},{'raw_status':''},{'entity_type':''}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cc.final_four_search_evidence({'state':'NV','query':q,'complete':True,'verification_pending':False,
                                              'total':1,'rows':[{**row,**changes}]},'NV',q)
        with self.assertRaises(ValueError):
            cc.final_four_search_evidence({'state':'NV','query':q,'complete':True,'verification_pending':False,
                                          'total':2,'rows':[row,row]},'NV',q)

    def test_nv_unsupported_matching_record_prevents_an_inactive_only_conclusion(self):
        def mixed(q):
            payload = self.provider(q)
            if q['operation'] == 'search':
                payload['rows'].append({**self.nvrow, 'identifier':'NV123456789',
                    'entity_type':'Foreign Entities Not Required to Register In Nevada'})
                payload['total'] = 2
            else:
                payload['fields']['Entity Status'] = 'Withdrawn'
                if q['identifier']=='NV123456789':
                    payload['fields']['NV Business ID']=q['identifier']
                    payload['fields']['Entity Type']='Foreign Entities Not Required to Register In Nevada'
            return payload
        result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', mixed)
        self.assertEqual(result.status, 'Unable to Confirm')
        self.assertIn('filing scope', result.source_note)

    def test_nv_charity_only_registration_full_lookup_and_dates(self):
        def provider(q):
            self.calls.append(q)
            if q['operation']=='search':
                row={'name':NV_SOLICITATION['Entity Name'],'identifier':NV_SOLICITATION['NV Business ID'],
                     'entity_type':NV_SOLICITATION['Entity Type'],'raw_status':'Registered'}
                return {'state':'NV','query':q,'complete':True,'verification_pending':False,'total':1,'rows':[row]}
            return {'query':q,'complete':True,'fields':copy.deepcopy(NV_SOLICITATION),
                    'source_url':self.nvurl,'filings':copy.deepcopy(NV_SOLICITATION_FILINGS)}
        org=cc.checker.Organization('Five Below Foundation','82-5406623')
        result=cc.final_four_browser_lookup(org,'NV',provider)
        self.assertTrue(result.success);self.assertEqual(result.status,'Current')
        self.assertIn('source-confirmed filing history',result.source_note)
        self.assertIn('field displays No',result.source_note)
        self.assertNotIn('does not establish a separate',result.source_note)
        dates=cc.final_four_date_metadata(result)
        filed=cc.final_four_filing_metadata(result,dates)
        self.assertEqual(dates['registration_date'],'2022-05-12')
        self.assertIn('Charitable Solicitation',dates['registration_date_source_label'])
        self.assertEqual(filed['renewal_filing_value'],'2026-05-05')
        self.assertEqual(filed['renewal_filing_label'],'Solicitation statement filed')

    def test_nv_wrong_or_offsite_detail_link_is_rejected(self):
        original = self.nvurl
        for url in ['', 'javascript:void(0)', 'https://example.com/record',
                    original.replace('Manage-Business', 'Manage-Agent'),
                    original.replace('d1b62c76-d5af-4ff3-b07d-038b7fa8d854', '-'*36)]:
            with self.subTest(url=url):
                self.nvurl = url
                with self.assertRaises(ValueError): cc.final_four_browser_lookup(self.orgs['NV'], 'NV', self.provider)
        self.nvurl = original

    def test_nv_detail_is_requested_by_observed_business_id_not_guessed_url(self):
        result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', self.provider)
        self.assertEqual([q for q in self.calls if q['operation'] == 'detail'],
                         [{'state': 'NV', 'operation': 'detail', 'identifier': NV['NV Business ID']}])
        self.assertEqual(result.source_url, self.nvurl)

    def test_deadline_does_not_start_another_query_or_borrow_other_state_time(self):
        with self.assertRaises(TimeoutError):
            cc.final_four_browser_lookup(self.orgs['AL'], 'AL', self.provider, deadline=time.monotonic()-1)
        self.assertEqual(self.calls, [])

    def test_missing_name_does_not_produce_unsearched_negative(self):
        with self.assertRaises(ValueError):
            cc.final_four_browser_lookup(cc.checker.Organization('', '123456789'), 'AL', self.provider)
        self.assertFalse(self.calls)

    def test_tn_registration_and_filed_period_remain_separate_from_expiration(self):
        result = cc.final_four_browser_lookup(self.orgs['TN'], 'TN', self.provider)
        dates = cc.registration_date_metadata(result, result.status)
        filed = cc.renewal_filing_metadata(result, dates, result.status)
        self.assertEqual(dates['registration_date'], '1999-09-13')
        self.assertEqual(dates['registration_date_type'], 'registry_registration_date')
        self.assertFalse(dates['renewal_date'])
        self.assertEqual(filed['renewal_filing_value'], '2024-12-31')
        self.assertEqual(filed['renewal_filing_type'], 'filed_period_end')
        self.assertEqual(result.computed_due_date, '2026-11-27')

    def test_nc_extension_application_does_not_replace_actual_renewal_filing(self):
        result = cc.final_four_browser_lookup(self.orgs['NC'], 'NC', self.provider)
        dates = cc.registration_date_metadata(result, result.status)
        filed = cc.renewal_filing_metadata(result, dates, result.status)
        self.assertFalse(dates['registration_date'])
        self.assertEqual(dates['renewal_date'], '2025-11-17')
        self.assertEqual(filed['renewal_filing_value'], '2025-11-17')
        self.assertEqual(filed['renewal_filing_type'], 'renewal_filing_date')
        self.assertEqual(result.computed_due_date, '2026-11-15')
        self.assertIn('extension end date', result.source_note)
        self.assertIn('/charities_filings/', dates['renewal_date_source_url'])

    def test_nv_formation_and_due_dates_do_not_become_renewal(self):
        result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', self.provider)
        dates = cc.registration_date_metadata(result, result.status)
        self.assertFalse(any(dates.values()))
        self.assertFalse(any(cc.renewal_filing_metadata(result, dates, result.status).values()))

    def test_unconfirmed_and_wrong_selected_record_dates_remain_blank(self):
        for state in self.orgs:
            result = cc.final_four_browser_lookup(self.orgs[state], state, self.provider)
            for status in ['Needs Review', 'Unable to Confirm', 'Not Registered']:
                dates = cc.registration_date_metadata(result, status)
                self.assertFalse(any(dates.values()))
                self.assertFalse(any(cc.renewal_filing_metadata(result, dates, status).values()))
            result.matched_registry_identifier = 'WRONG'
            self.assertFalse(any(cc.registration_date_metadata(result, result.status).values()))

    def test_date_metadata_has_no_network_or_status_mutation(self):
        for state, org in self.orgs.items():
            result = cc.final_four_browser_lookup(org, state, self.provider)
            before = copy.deepcopy(vars(result))
            with patch.object(cc, 'identity_fetch', side_effect=AssertionError('No optional date requests')):
                dates = cc.registration_date_metadata(result, result.status)
                cc.renewal_filing_metadata(result, dates, result.status)
            self.assertEqual(vars(result), before)

    def test_nv_annual_list_is_latest_filing_not_formation_or_due_date(self):
        def with_filings(q):
            data = self.provider(q)
            if q['operation'] == 'detail': data['filings'] = copy.deepcopy(NV_FILINGS)
            return data
        result = cc.final_four_browser_lookup(self.orgs['NV'], 'NV', with_filings)
        dates = cc.registration_date_metadata(result, result.status)
        filed = cc.renewal_filing_metadata(result, dates, result.status)
        self.assertFalse(any(dates.values()))
        self.assertEqual(filed['renewal_filing_value'], '2025-10-29')
        self.assertEqual(filed['renewal_filing_label'], 'Annual list filed')
        self.assertEqual(result.computed_due_date, '2026-12-31')

    def test_optional_history_failure_preserves_confirmed_status(self):
        for state in ['NC', 'NV', 'TN']:
            def broken(q):
                data = self.provider(q)
                if q['operation'] == 'detail':
                    if state == 'TN': data['fields']['financial_count'] = 100
                    else: data['filings'] = {'complete': False}
                return data
            with self.subTest(state=state):
                result = cc.final_four_browser_lookup(self.orgs[state], state, broken)
                self.assertTrue(result.success)
                self.assertIn(result.status, ['Current', 'Upcoming Filing'])
                dates = cc.registration_date_metadata(result, result.status)
                self.assertFalse(any(cc.renewal_filing_metadata(result, dates, result.status).values()))
                self.assertIn('remains blank', result.source_note)

    def test_nv_incomplete_and_wrong_record_histories_are_rejected(self):
        row = cc.nv_charity_detail_evidence(NV, NV['NV Business ID'])
        for changes in [{'identifier': 'NV0000000'}, {'name': 'Other Foundation'}, {'total': 19}, {'complete': False},
                        {'rows': [NV_FILINGS['rows'][0]] * 2},
                        {'rows': [['10/29/2099', '10/29/2025', '20255271827', 'Annual List', 'Online', '3'], NV_FILINGS['rows'][1]]}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                cc.nv_charity_filings_evidence(row, {**NV_FILINGS, **changes})

    def test_nv_foreign_qualification_needs_explicit_filing_and_agreeing_formation(self):
        row = cc.nv_charity_detail_evidence(NV, NV['NV Business ID'])
        filing = ['12/10/2012', '12/10/2012', '20120833156-91', 'Foreign Qualification', 'Walk-in', '2']
        history = {**NV_FILINGS, 'rows': [*NV_FILINGS['rows'], filing], 'total': 3}
        parsed = cc.nv_charity_filings_evidence(row, history)
        self.assertEqual(parsed['initial'], date(2012, 12, 10))
        self.assertEqual(parsed['initial_label'], 'Foreign Qualification — Filed Date')
        self.assertIsNone(cc.nv_charity_filings_evidence({**row, 'entity_formation': date(2013, 1, 1)}, history)['initial'])
        self.assertIsNone(cc.nv_charity_filings_evidence(row, NV_FILINGS)['initial'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
