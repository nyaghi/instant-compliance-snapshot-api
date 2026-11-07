import json,re,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from bs4 import BeautifulSoup
import CharityClarity_WA_NM_checker as w
D=Path(__file__).parent/'fixtures/gates29-30'
class Anchors:
 def __init__(self,items):self.items=items
 def filter(self,has_text):return Anchors([x for x in self.items if has_text.search(x.get_text())])
 def count(self):return len(self.items)
 def is_visible(self):return all('display:none' not in str(x.get('style','')) for x in self.items)
class Page:
 def __init__(self,html):self.dom=BeautifulSoup(html,'html.parser')
 def locator(self,selector):return Anchors(self.dom.select(selector))
class WashingtonFallback(unittest.TestCase):
 def run_case(self,html,rows=None):
  raw=json.loads((D/'WA-PUBLIC-NAME-RESPONSE.json').read_text())['body'] if rows is None else json.dumps(rows)
  page=Page(html);tracker=dict(completed=1,pending=0,failed=0,lastStatus=200,lastText=raw)
  with patch.object(w,'switch_to_name_mode'),patch.object(w,'fill_name_and_search',return_value=True),patch.object(w,'safe_wait_for_network_idle'),patch.object(w.time,'sleep'),patch.object(w,'wait_for_result_link_or_no_value',return_value=object()),patch.object(w,'wa_search_tracker_state',return_value=tracker):
   return w.wa_name_fallback_result_link(page,NS(ein='872410117',organization_name='Human Appeal Inc.'))
 def test_actual_href_less_source_reaches_qualified_review(self):
  html=(D/'WA-PUBLIC-RESULT-MARKUP.html').read_text();self.assertIsNotNone(self.run_case(html))
 def test_unique_visible_exact_row_required(self):
  for inner in ['<a>HUMAN APPEAL INC. OTHER</a>','<a>HUMAN APPEAL INC.</a><a>HUMAN APPEAL INC.</a>','<a style="display:none">HUMAN APPEAL INC.</a>','<a>DIFFERENT</a>']:
   with self.subTest(inner=inner):self.assertIsNone(self.run_case('<table id="tblCFSearch"><tbody>'+inner+'</tbody></table>'))
 def test_outside_table_and_identity_mismatch_cannot_pass(self):
  self.assertIsNone(self.run_case('<a>HUMAN APPEAL INC.</a>'))
  rows=json.loads(json.loads((D/'WA-PUBLIC-NAME-RESPONSE.json').read_text())['body']);rows[0]['FEINNumber']='111111111'
  self.assertEqual(self.run_case((D/'WA-PUBLIC-RESULT-MARKUP.html').read_text(),rows),'NO_VALUE')
if __name__=='__main__':unittest.main()
