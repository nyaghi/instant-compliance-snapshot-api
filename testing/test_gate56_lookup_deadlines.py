import json
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import registry_snapshot_server as cc
from deployment.co_budget import STOP

ORG = json.loads((pathlib.Path(__file__).parent/'fixtures/gate55/LOCAL-70.json').read_text())


class LookupDeadlines(unittest.TestCase):
    def test_co_completed_ein_only_at_name_deadline(self):
        self.assertEqual(len({o['ein'] for o in ORG}),70)
        for record in ORG:
            org=SimpleNamespace(organization_name=record['name'],ein=record['ein'])
            for expired in (True,False):
                with self.subTest(ein=org.ein, expired=expired):
                    ein_result=cc.checker.StateResult(org.organization_name,org.ein,'CO','Not Registered','https://www.coloradosos.gov/ccsa/pages/search/basic.xhtml',success=True)
                    transport=cc.checker.StateResult(org.organization_name,org.ein,'CO','Site Not Reachable',ein_result.source_url,error='CO error: Page.goto: Timeout 57ms exceeded.')
                    token=STOP.set(20)
                    try:
                        with patch.object(cc.time,'monotonic',side_effect=[19.9,20.01 if expired else 19.93]),patch.object(cc,'organization_name_variants',return_value=[record['name']]),patch.object(cc.checker,'search_co',return_value=transport):
                            got=cc.co_light_name_fallback(None,org,ein_result,org.ein)
                        self.assertEqual(got.status,'Not Registered' if expired else 'Site Not Reachable')
                    finally:STOP.reset(token)

    def test_fl_seventy_explicit_empty_postbacks_and_unsettled_postbacks(self):
        for record in ORG:
            org=SimpleNamespace(organization_name=record['name'],ein=record['ein'])
            names=[org.organization_name, 'The '+org.organization_name]
            for kind in ('empty','loading','wrong-form','row-present'):
                empty = kind == 'empty'
                page=MagicMock();page.url=cc.FL_CHECK_A_CHARITY_URL
                page.expect_navigation.return_value.__enter__.return_value.value=SimpleNamespace(status=200)
                page.locator.return_value.inner_text.return_value={'empty':'No matching records found','loading':'Loading','wrong-form':'No matching records found','row-present':'CH12345 | No matching records found'}[kind]
                page.fill.side_effect=lambda text,**kw:setattr(page.input_value,'return_value','OTHER' if kind=='wrong-form' else text)
                with self.subTest(ein=org.ein,kind=kind),patch.object(cc,'reviewed_queries_first',return_value=names.copy()),patch.object(cc,'fl_business_lookup_enabled',return_value=False),patch.object(cc,'fl_completed_search_form_available',return_value=True),patch.object(cc.checker,'find_visible_input',return_value=page),patch.object(cc,'readable_page_text',return_value='No matching records found') as settled,patch.object(cc.time,'sleep') as pause:
                    result=cc.search_fl(page,org)
                    self.assertTrue(result.success);self.assertEqual(result.status,cc.checker.STATUS_NOT_REGISTERED)
                    self.assertEqual([v.args[0] for v in page.fill.call_args_list if v.args[0]],names)
                    self.assertEqual(page.expect_navigation.call_count,2)
                    self.assertEqual(settled.call_count,2)
                    self.assertEqual(sum(call.args==(0.5,) for call in pause.call_args_list),0 if empty else 2)

