"""Reproduce the archived Georgia grid with bounded primary-detail fixtures."""
import re
import unittest
from unittest.mock import patch
from testing.run_il_ga_guardrails import cc, ga_html, search_row
from deployment.state_snapshots import matching_reference

NAME = 'American Civil Liberties Union Foundation, Inc.'
AFFILIATE = 'American Civil Liberties Union Foundation of Georgia, Inc.'
EIN = '136213516'

def row(name, identifier, index):
    return search_row(name, identifier, f'00000000-0000-0000-0000-{index:012d}')

class HistoricalRowTests(unittest.TestCase):
    def check(self, rows, legacy_status='Expired', legacy_name=NAME):
        org=cc.checker.Organization(NAME,EIN)
        details=[]
        def evidence(query):
            if 'identifier' not in query:
                return cc.il_ga_clean_evidence(dict(query=query,complete=True,total=len(rows),rows=rows),query)
            selected=next(r for r in rows if r['detail_key']==query['detail_key'])
            identifier=selected['identifier']
            details.append(identifier)
            body=ga_html(full_name=selected['name'] if identifier else legacy_name,license_no=identifier,
                         status='Active' if identifier else legacy_status,expiry='12/31/2099' if identifier else '')
            if not identifier:
                body=re.sub(r'<span id="_ctl34__ctl1_license_no"></span>','',body)
            return cc.il_ga_clean_evidence(dict(query=query,complete=True,body=body),query)
        with patch.object(cc,'licensed_charity_names',return_value=([NAME],[])), \
             patch.object(cc,'public_profile_for_ein',return_value={}), \
             patch.object(cc,'registry_cross_state_identity',return_value={}):
            return cc.il_ga_browser_lookup(org,'GA',evidence),details

    def test_same_name_retired_row_does_not_hide_numbered_record_or_original(self):
        for rows in ([row(NAME,'',1),row(AFFILIATE,'CH012441',2),row(NAME,'CH05756',3)],
                     [row(NAME,'CH05756',3),row(NAME,'',1),row(AFFILIATE,'CH012441',2)]):
            result,details=self.check(rows)
            self.assertTrue(result.success)
            self.assertEqual(result.matched_registry_identifier,'CH05756')
            self.assertIn('',details)
            self.assertIn('expired, unnumbered',result.source_note)
            refs=[dict(state='GA',ein=EIN,identifier=identifier,record_name=name,operation=op,url=url)
                  for identifier,name,op,url in [('CH05756',NAME,'search','list'),('CH012441',AFFILIATE,'detail','affiliate'),
                                                ('CH05756',NAME,'detail','correct')]]
            self.assertEqual(matching_reference(vars(result),refs)['url'],'correct')

    def test_missing_number_cannot_supply_a_registration_or_affiliate_match(self):
        for rows in ([row(NAME,'',1)], [row(NAME,'',1),row(AFFILIATE,'CH012441',2)]):
            with self.assertRaisesRegex(ValueError,'could not be reconciled'):self.check(rows)
        for status,name in [('Active',NAME),('Expired',AFFILIATE)]:
            with self.assertRaises(ValueError):
                self.check([row(NAME,'',1),row(NAME,'CH05756',3)],status,name)
