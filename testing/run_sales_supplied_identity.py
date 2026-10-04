"""Offline adapter-level controls for supplied names, not discovered aliases."""
import time
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
import registry_snapshot_server as cc
from testing.capacity_lab.test_sc_possible_identity import SouthCarolinaIdentityTests


class SuppliedIdentityTests(unittest.TestCase):
    def setUp(self):
        token = cc.REVIEWED_NAME_CONTEXT.set({})
        self.addCleanup(cc.REVIEWED_NAME_CONTEXT.reset, token)

    def test_complete_supplied_names_are_accepted_without_discovery(self):
        pairs = [
            ('United Animal Nations — RedRover', 'United Animal Nations'),
            ('United Animal Nations — RedRover', 'United Animal Nations dba Redrover'),
            ('Beacon Literacy Network — ReadTogether', 'Beacon Literacy Network, Inc.'),
            ('Harbor Animal Rescue / RescueBridge', 'Harbor Animal Rescue'),
            ('Harbor Animal Rescue / RescueBridge', 'Harbor Animal Rescue AKA RescueBridge'),
        ]
        with patch.object(cc, 'discover_organization_names', side_effect=AssertionError('Discovery forbidden')):
            for entered, candidate in pairs:
                with self.subTest(candidate=candidate):
                    score = cc.score_candidate(entered, '123456789', {'name': candidate})
                    self.assertEqual(score['decision'], 'accepted')
                    self.assertEqual(score['reason'], 'MATCH_SUPPLIED_COMPLETE_NAME')
                    self.assertEqual(cc.known_names_for_ein('123456789'), [])

    def test_adverse_and_shortened_names_are_not_promoted(self):
        pairs = [
            ('United Animal Nations — RedRover', 'United Animal Nations Foundation'),
            ('United Animal Nations — RedRover', 'RedRover'),
            ('United Animal Nations — RedRover', 'United Animal Nations DBA Another Charity'),
            ('Beacon Literacy Network — ReadTogether', 'Beacon Literacy'),
            ('Beacon Literacy Network — ReadTogether', 'Beacon Literacy Network California Chapter'),
            ('University of California — Los Angeles', 'University of California'),
            ('Make-A-Wish Foundation', 'Make'),
            ('Warrior-Scholar Project Foundation', 'Warrior'),
            ('Community Foundation — Giving', 'Community Foundation'),
        ]
        for entered, candidate in pairs:
            with self.subTest(entered=entered, candidate=candidate):
                self.assertFalse(cc.supplied_complete_name_identity_match(entered, candidate))
                self.assertNotEqual(cc.score_candidate(entered, '123456789', {'name':candidate})['decision'], 'accepted')

    def test_different_ein_overrides_supplied_name_and_exact_ein_stays_primary(self):
        entered='Beacon Literacy Network — ReadTogether'
        self.assertEqual(cc.score_candidate(entered,'123456789',{'name':'Beacon Literacy Network','ein':'999999999'})['reason'],'REJECT_DIFFERENT_EIN')
        self.assertEqual(cc.score_candidate(entered,'123456789',{'name':'Beacon Literacy Network','ein':'123456789'})['reason'],'MATCH_EIN_EXACT')

    def test_georgia_adapter_accepts_explicit_supplied_legal_dba_without_extra_names(self):
        org=cc.checker.Organization('United Animal Nations — RedRover','680124097')
        row={'name':'United Animal Nations dba Redrover','ein':'','identifier':'CH002021',
             'location':'','status':'Current','raw_status':'Active','expiration':date(2027,12,31)}
        with patch.object(cc,'reconciled_registry_address',return_value={'decision':'unavailable'}):
            selected,review=cc.select_licensed_charity(org,[row],'GA',time.monotonic()+2)
        self.assertIs(selected,row)
        self.assertEqual(review,'')
        self.assertEqual(row['match']['reason'],'MATCH_SUPPLIED_COMPLETE_NAME')

    def test_conflicting_address_remains_reviewed(self):
        org=cc.checker.Organization('Beacon Literacy Network — ReadTogether','123456789')
        row={'name':'Beacon Literacy Network','ein':'','identifier':'fixture','location':'Other, TX',
             'status':'Current','raw_status':'Active','expiration':date(2027,12,31)}
        with patch.object(cc,'reconciled_registry_address',return_value={'decision':'conflict'}), \
             patch.object(cc,'licensed_charity_street_evidence',return_value={}):
            self.assertEqual(cc.licensed_charity_identity(org,row,'GA',time.monotonic()+2),'conflict')

    def test_south_carolina_does_not_fetch_filing_for_full_supplied_name(self):
        helper=SouthCarolinaIdentityTests()
        result,filing,_=helper.run_lookup('United Animal Nations','',name='United Animal Nations — RedRover')
        self.assertTrue(result.success)
        self.assertEqual(result.matched_registry_identifier,'P1234')
        filing.assert_not_called()

    def test_mississippi_accepts_component_and_stops_without_extra_queries(self):
        org=cc.checker.Organization('United Animal Nations — RedRover','680124097')
        external=SimpleNamespace(status='Current',organization_name='United Animal Nations',
          matched_registry_name='United Animal Nations',raw_status_text='Active',source_note='',success=True)
        module=SimpleNamespace(Organization=lambda **kw:SimpleNamespace(**kw))
        with patch.object(cc,'state_batch_modules',return_value={'fixture':module}), \
             patch.object(cc,'load_state_batch_bundle',return_value=SimpleNamespace(STATE_TO_MODULE={'MS':'fixture'})), \
             patch.object(cc,'ms_name_search_plan',return_value=['United Animal Nations','RedRover']), \
             patch.object(cc,'search_ms_fast',return_value=external) as search, \
             patch.object(cc,'copy_external_result',side_effect=lambda o,s,r:r), \
             patch.object(cc,'ms_legal_description_identity',side_effect=AssertionError('No extra identity fetch')):
            result=cc.search_batch_browser_state(Mock(),org,'MS')
        self.assertEqual(result.status,'Current')
        self.assertEqual(search.call_count,1)
        self.assertEqual(result.queries_attempted,['United Animal Nations'])

    def test_maine_query_cap_keeps_supplied_components_and_literal_and(self):
        for name,parts in [
                ('United Animal Nations — RedRover', ['United Animal Nations','RedRover']),
                ('Beacon Literacy Network / ReadTogether',['Beacon Literacy Network','ReadTogether']),
                ('Harbor & River Rescue — SafeAnimals',['Harbor & River Rescue','SafeAnimals'])]:
            with self.subTest(name=name):
                org=cc.checker.Organization(name,'123456789')
                queries=cc.me_fast_direct_query_variants(org)
                for part in parts:self.assertIn(part,queries)
                self.assertLessEqual(len(queries),cc.ME_FAST_DIRECT_CONFIRMATION_MAX_VARIANTS)
        org=cc.checker.Organization('Foundation for Food & Agriculture Research','471559027')
        self.assertIn('Foundation for Food and Agriculture Research',cc.me_fast_direct_query_variants(org))


if __name__=='__main__':unittest.main(verbosity=2)
