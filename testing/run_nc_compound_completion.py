"""Offline composite-name completion controls. Registry access is mocked."""
import copy
import time
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc
from testing.run_final_four_source_guardrails import NC, NC_PROFILE


class CompoundCompletion(unittest.TestCase):
    def lookup(self, legal='United Animal Nations', brand='RedRover', *, address='corroborated', status=None, fail_component=False, aliases=None):
        name=f'{legal} — {brand}'
        org=cc.checker.Organization(name,'68-0124097')
        calls=[]
        card={**NC,'CSL Legal Name':legal+', Inc.'}
        profile={**NC_PROFILE,'Name':legal+', Inc.'}
        if status:
            card['Status']=profile['Status']=status
        def provider(q):
            calls.append(copy.deepcopy(q))
            if q['operation']=='detail':
                return {'query':q,'complete':True,'fields':profile}
            if q['name']=='Later Campaign' or fail_component and q['name']==brand:
                raise ValueError('Fixture later search verification failed')
            rows=[card] if q['name'].casefold()==legal.casefold() else []
            return {'state':'NC','query':q,'complete':True,'verification_pending':False,'rows':rows,'total':len(rows)}
        aliases=aliases or [legal,'Later Campaign']
        token=cc.REVIEWED_NAME_CONTEXT.set({'680124097':tuple(aliases)})
        try:
            with patch.object(cc,'trial_identity',return_value={'origin':'fixture'}), \
                 patch.object(cc,'licensed_charity_names',return_value=([name,*aliases],[])), \
                 patch.object(cc,'reconciled_registry_address',return_value={'decision':address,'basis':'Fixture EIN-linked office'}), \
                 patch.object(cc,'licensed_charity_street_evidence',return_value={}):
                return cc.final_four_browser_lookup(org,'NC',provider,time.monotonic()+10),calls
        finally:
            cc.REVIEWED_NAME_CONTEXT.reset(token)

    def test_confirmed_entered_components_finish_before_unneeded_campaign(self):
        for legal,brand in [('United Animal Nations','RedRover'),('Example Education Institute','Bright Futures')]:
            with self.subTest(legal=legal):
                result,calls=self.lookup(legal,brand)
                self.assertTrue(result.success)
                expected = ([f'{legal} — {brand}'] if len(cc.distinctive_match_tokens(brand)) >= 2 else [])
                self.assertEqual([q.get('name') for q in calls if q['operation']=='search'],
                                 [*expected,legal,brand])

    def test_component_must_complete_before_early_exit(self):
        with self.assertRaisesRegex(ValueError,'later search'):
            self.lookup(fail_component=True)

    def test_reported_discovery_list_stops_after_both_entered_components(self):
        result,calls=self.lookup(aliases=['UNITED ANIMAL NATIONS','UNITED ANIMAL NATIONS DBA REDROVER',
            'UNITED ANIMAL NATIONS DBA RED ROVER','RedRover','RedRover Responders','RedRover Readers','RedRover Relief','Later Campaign'])
        self.assertTrue(result.success)
        self.assertEqual([q.get('name') for q in calls if q['operation']=='search'],['United Animal Nations','RedRover'])

    def test_short_name_component_does_not_enable_exit(self):
        with self.assertRaisesRegex(ValueError,'later search'):
            self.lookup('Aeon','Broad Foundation')

    def test_component_gate_is_trial_only_and_never_accepts_an_unentered_alias(self):
        org=cc.checker.Organization('Example Education Institute / Bright Future','12-3456789')
        queries=['Example Education Institute','Bright Future']
        for row in [{'name':'Different Discovered Alias'},{'name':'Example Education Institute Local Chapter'}]:
            with patch.object(cc,'trial_identity',return_value={'origin':'fixture'}):
                self.assertFalse(cc.nc_entered_components_complete(org,row,queries))
        with patch.object(cc,'trial_identity',return_value=None):
            self.assertFalse(cc.nc_entered_components_complete(org,{'name':'Example Education Institute'},queries))

    def test_unavailable_or_conflicting_address_cannot_enable_component_exit(self):
        for address in ['unavailable','conflict','different_ein']:
            with self.subTest(address=address),self.assertRaisesRegex(ValueError,'later search'):
                self.lookup(address=address)

    def test_adverse_component_must_still_search_remaining_aliases(self):
        with self.assertRaisesRegex(ValueError,'later search'):
            self.lookup(status='Revoked')

    def test_long_name_uses_complete_all_words_evidence_to_avoid_rate_limit(self):
        org=cc.checker.Organization('Example Association for Environmental Sustainability and Education','12-3456789')
        queries=[]
        def provider(q):
            queries.append(q)
            return {'state':'NC','query':q,'complete':True,'verification_pending':False,
                    'rows':[],'total':0,'search_mode':q.get('search_mode','STARTS_WITH')}
        with patch.object(cc,'trial_identity',return_value={'origin':'fixture'}):
            result=cc.final_four_browser_lookup(org,'NC',provider,time.monotonic()+10)
        self.assertEqual(result.status,'Not Registered')
        self.assertEqual(len(queries),1)
        self.assertEqual(queries[0]['search_mode'],'ALL_WORDS')
        self.assertTrue(cc.nc_all_words_covers(queries[0]['name'],org.organization_name))

    def test_incomplete_all_words_probe_never_proves_no_record(self):
        org=cc.checker.Organization('Example Association for Environmental Sustainability and Education','12-3456789')
        def blocked(q):
            raise ValueError('NC HTTP 429')
        with patch.object(cc,'trial_identity',return_value={'origin':'fixture'}), \
             self.assertRaisesRegex(ValueError,'429'):
            cc.final_four_browser_lookup(org,'NC',blocked,time.monotonic()+10)

    def test_long_common_opening_words_keep_existing_search_plan(self):
        for name in ['Planned Parenthood Minnesota, North Dakota, South Dakota',
                     'Consumer Advocates for Smoke-free Alternatives Association — CASAA']:
            with self.subTest(name=name):
                org=cc.checker.Organization(name,'12-3456789')
                required,generated=cc.licensed_charity_names(org)
                self.assertEqual(cc.nc_primary_all_words_probe(required[0],generated),'')

if __name__=='__main__':
    unittest.main()
