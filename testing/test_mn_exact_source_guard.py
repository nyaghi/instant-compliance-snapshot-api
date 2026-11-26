import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from deployment import mn_exact_detail as detail


class ExactSource(unittest.TestCase):
    def test_limited_name_normalization_requires_exact_ein_and_state_label(self):
        page = Mock()
        ein = '111630830'
        page.url = detail.DETAIL_URL + '?FederalID=111630830&Yr=CURR&cmdSearch=View'
        page.goto.return_value.status = 200
        fields = dict(name='St. Johns University',id='Federal ID# 111630830',status='EXEMPT',emptyPeriod=True)
        page.locator.return_value.evaluate.return_value = fields
        read = lambda name: detail.find(page, ein, [name], str.casefold, lambda: 5000)
        self.assertEqual(read("St. John's University")[1],'Exempt')
        self.assertIsNone(read('St. Johns Foundation'))
        fields['id'] = 'Federal ID# 111630831'
        self.assertIsNone(read("St. John's University"))

    def test_legacy_initials_require_same_base_and_ein(self):
        page = Mock()
        ein = "135563422"
        page.url = detail.DETAIL_URL + "?FederalID=135563422&Yr=CURR&cmdSearch=View"
        page.goto.return_value.status = 200
        fields = dict(name="Catholic Relief Services - USCC", id="Federal ID# 135563422",
                      status="Exempt", emptyPeriod=True)
        page.locator.return_value.evaluate.return_value = fields
        approved = ["Catholic Relief Services- U.S. Catholic Conference"]
        self.assertEqual(detail.find(page, ein, approved, str.casefold, lambda: 5000)[1], "Exempt")
        self.assertIsNone(detail.find(page, ein, ["Catholic Relief Services"], str.casefold, lambda: 5000))
        fields["name"] = "Catholic Relief Foundation - USCC"
        self.assertIsNone(detail.find(page, ein, approved, str.casefold, lambda: 5000))
        fields.update(name="Catholic Relief Services - USCC", id="Federal ID# 135563423")
        self.assertIsNone(detail.find(page, ein, approved, str.casefold, lambda: 5000))

    def test_source_failures_remain_unavailable(self):
        page = Mock()
        page.url = detail.DETAIL_URL
        for status in (403,408,429,500,503):
            page.goto.return_value.status = status
            with self.subTest(status=status), self.assertRaises(TimeoutError):
                detail.find(page,'590624458',['University of Miami'],str.casefold,lambda:5000)
        result=detail.unavailable(SimpleNamespace())
        self.assertFalse(result.success)
        self.assertEqual(result.status,'Site Not Reachable')
