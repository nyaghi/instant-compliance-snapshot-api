"""Regression for the state's literal @ search and reviewed alias priority."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
ROW='''<tr><td><b class="forge-typography--headline6">OPPORTUNITY@WORK INC</b><b>Credential</b><p>CHR.0068562</p><b>Credential Description</b><p>PUBLIC CHARITY</p><b>Status</b><p>ACTIVE</p><b>Status Reason</b><p>CURRENT</p></td></tr>'''
DETAIL='Name and Address OPPORTUNITY@WORK INC Address 1100 CONNECTICUT AVE NW STE 430 WASHINGTON DC 20036 Registration CHR.0068562 Expiration Date 11/30/2027 Status ACTIVE'
class ConnecticutLiteralNameTests(unittest.TestCase):
    def setUp(self):self.token=c.REVIEWED_NAME_CONTEXT.set({})
    def tearDown(self):c.REVIEWED_NAME_CONTEXT.reset(self.token)
    def check_name(self,name,aliases):
        c.REVIEWED_NAME_CONTEXT.set({'813214432':tuple(aliases)})
        queries=[]
        def query(session,fields,headers,value,timeout):
            queries.append(value)
            return 'Showing 1 result(s).'+ROW if value=='Opportunity@Work' else 'Showing 0 result(s).'
        with patch.object(c,'ct_direct_prepare_session',return_value=(None,{},{})),patch.object(c,'ct_direct_post_query',side_effect=query),patch.object(c,'ct_direct_detail_text',return_value=DETAIL):
            result=c.search_ct_direct(c.checker.Organization(name,'81-3214432'))
        self.assertEqual(c.public_status(result),'Current')
        self.assertEqual(result.matched_registry_identifier,'CHR.0068562')
        return queries
    def test_entered_name_keeps_literal_at_before_generated_queries(self):
        self.assertEqual(self.check_name('Opportunity@Work, Inc.',['Opportunity at Work Inc']),['Opportunity@Work'])
    def test_reviewed_at_name_precedes_generated_fallbacks(self):
        self.assertEqual(self.check_name('Opportunity at Work Inc',['Opportunity@Work, Inc.']),['Opportunity at Work','Opportunity@Work'])
    def test_default_query_spelling_remains_unchanged(self):
        self.assertEqual(c.equivalent_name_queries('Opportunity@Work, Inc.',''),['Opportunity Work'])
        for name in ['Children\u2019s Hospital, Inc.','Health & Safety, Inc.','National Board - Boston','Ordinary Foundation']:
            with self.subTest(name=name):
                self.assertEqual(c.equivalent_name_queries(name,'',preserve_at=True),c.equivalent_name_queries(name,''))
if __name__=='__main__':unittest.main(verbosity=2)
