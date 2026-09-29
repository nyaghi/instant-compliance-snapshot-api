"""Candidate-equivalent DC queries and verified NY duplicate-record navigation."""
import ast
from pathlib import Path
import random
import re
import subprocess
import unittest
from unittest.mock import MagicMock, patch
import registry_snapshot_server as cc
from testing.capacity_lab.transport_scope import remove_transport_recovery


class TransportControls(unittest.TestCase):
    def page(self):
        p=MagicMock();p.url='https://charities-search.ag.ny.gov/RegistrySearch'
        p.get_by_role.return_value.is_enabled.return_value=True
        p.go_back.side_effect=lambda **kw:setattr(p,'url',p._cc_ny_search_url)
        return p

    def invoke(self,p,operation,params):
        with patch.object(cc,'NYBrowserResponse',side_effect=lambda r:r):
            return cc.ny_browser_registry_response(p,operation,params,12)

    def search(self,p):self.invoke(p,'RegistrySearch',{'ein':'320033325'})

    def test_first_detail_keeps_existing_verified_search_sequence(self):
        p=self.page();self.search(p)
        self.invoke(p,'RegistryDetail',{'orgID':'first'})
        p.go_back.assert_not_called()
        self.assertEqual(p._cc_ny_search_url,'https://charities-search.ag.ny.gov/RegistrySearch')
        p.get_by_role.assert_any_call('link',name='first',exact=True)

    def test_next_detail_returns_to_results_before_click(self):
        p=self.page();self.search(p)
        self.invoke(p,'RegistryDetail',{'orgID':'first'})
        p.url='https://charities-search.ag.ny.gov/RegistryDetail/first'
        self.invoke(p,'RegistryDetail',{'orgID':'second'})
        p.go_back.assert_called_once()
        p.wait_for_url.assert_called_once()
        self.assertEqual(p.wait_for_url.call_args.args[0],p._cc_ny_search_url)
        p.get_by_role.assert_any_call('link',name='second',exact=True)
        self.assertFalse(any(call.args==('button',) and call.kwargs.get('name')=='Verify' for call in p.get_by_role.call_args_list))

    def test_return_navigation_failure_does_not_open_wrong_candidate(self):
        p=self.page();self.search(p);p.url='https://charities-search.ag.ny.gov/RegistryDetail/first'
        p.go_back.side_effect=TimeoutError('history incomplete')
        p.get_by_role.reset_mock()
        with self.assertRaises(TimeoutError):self.invoke(p,'RegistryDetail',{'orgID':'second'})
        p.get_by_role.assert_not_called()

    def test_unconfirmed_results_url_is_not_a_completed_return(self):
        p=self.page();self.search(p);p.url='https://charities-search.ag.ny.gov/RegistryDetail/first'
        p.wait_for_url.side_effect=TimeoutError('wrong history entry')
        p.get_by_role.reset_mock()
        with self.assertRaises(TimeoutError):self.invoke(p,'RegistryDetail',{'orgID':'second'})
        p.get_by_role.assert_not_called()

    def test_search_retry_also_returns_and_refills_same_ein(self):
        p=self.page();self.search(p);p.url='https://charities-search.ag.ny.gov/RegistryDetail/first'
        self.search(p)
        p.go_back.assert_called_once()
        self.assertEqual(p.locator.return_value.fill.call_args_list[-1].args,('320033325',))
        self.assertEqual(p.locator.call_count,2)

    def test_name_fallback_clears_prior_ein_without_submitting_empty_ein(self):
        p=self.page();self.search(p);p.locator.reset_mock()
        self.invoke(p,'RegistrySearch',{'orgName':'Beacon Education Foundation'})
        p.get_by_role.assert_any_call('button',name='Clear fields',exact=True)
        p.locator.assert_called_once_with('#orgName')
        p.locator.return_value.fill.assert_called_with('Beacon Education Foundation',timeout=unittest.mock.ANY)

    def test_dc_redundant_patterns_removed_but_distinct_alias_retained(self):
        self.assertEqual(cc.dc_license_query_patterns(['Beacon Learning Foundation','Beacon Learning','Former Academy','Beacon Learning Foundation']),
                         ['%BEACON%LEARNING%','%FORMER%ACADEMY%'])
        self.assertEqual(cc.dc_license_query_patterns(['---','']),[])

    def test_dc_repeated_words_cannot_remove_a_broader_required_query(self):
        self.assertEqual(cc.dc_license_query_patterns(['Blue Blue Sky','Blue Sky']),['%BLUE%SKY%'])
        self.assertEqual(cc.dc_license_query_patterns(['AB CD','ABCD']),['%AB%CD%','%ABCD%'])

    def test_dc_query_union_is_identical_across_generated_candidate_sets(self):
        rng=random.Random(902526);words=['ALPHA','BETA','NORTH','SOUTH','ARTS','HEALTH','FUND']
        for _ in range(200):
            names=[' '.join(rng.choices(words,k=rng.randint(1,6))) for _ in range(8)]
            old=['%'+'%'.join(n.split())+'%' for n in names];new=cc.dc_license_query_patterns(names)
            candidates=names+[' '.join(rng.choices(words,k=rng.randint(1,12))) for _ in range(20)]
            for name in candidates:
                def matches(patterns):return any(re.fullmatch(p.replace('%','.*'),name,re.S) for p in patterns)
                self.assertEqual(matches(old),matches(new),(names,name,new))
            self.assertLessEqual(len(new),len(old))

    def test_entire_master_only_changes_dc_query_and_ny_history_transport(self):
        root=Path(__file__).resolve().parents[2]
        old=ast.parse(subprocess.check_output(['git','show','6eed5f9:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        remove_transport_recovery(new)
        self.assertEqual(ast.dump(old),ast.dump(new))


if __name__=='__main__':unittest.main(verbosity=2)
