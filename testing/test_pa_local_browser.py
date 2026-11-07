"""Local-only browser fixture: all requests fulfilled locally; no registry calls."""
import json,time,unittest
from types import SimpleNamespace as NS
from playwright.sync_api import sync_playwright
from deployment import pa_detail_evidence as pa

class LocalBrowser(unittest.TestCase):
 def test_original_detail_with_real_playwright_api(self):
  cells=['TEACH FOR ALL, INC.','','','101367','08/15/2027','26-2122566']+['']*6
  fields=dict(EntityName=cells[0],RegNum=cells[3],Expdt=cells[4],FederalID=cells[5])
  grid='<table><tr id="SearchResults">'+''.join('<td>'+v+'</td>' for v in cells)+'<td><i ng-click="search.redirectEntityDetails(row)" onclick="window.open(\''+pa.DETAIL+'\')">View</i></td></tr></table>'
  detail='<div id="panelEntityInfo">'+''.join('<label>'+k+'<input name="'+k+'" value="'+v+'" disabled></label>' for k,v in fields.items())+'</div>'
  detail+='<div class="cg-busy" style="position:fixed;inset:0;background:white">Loading</div><script>setTimeout(()=>document.querySelector(".cg-busy").style.display="none",600)</script>'
  html='<script>document.write(location.hash.includes("charitiesEntityDetails")?'+json.dumps(detail).replace('</script>','<\\/script>')+':'+json.dumps(grid)+');</script>'
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True)
   context=browser.new_context();context.route('**/*',lambda route:route.fulfill(status=200,body=html,content_type='text/html'))
   page=context.new_page();page.goto(pa.SEARCH)
   run=NS(state='PA',ein='262122566',visual_adapter_facts=[],documents=[])
   run.document=lambda *args,**kw:run.documents.append(args)
   token=pa.CURRENT.set(run);deadline=pa.DEADLINE.set(time.monotonic()+30)
   try:pa.capture(page,NS(ein=run.ein),NS(state='PA',success=True,status='Current',matched_registry_name=cells[0],matched_registry_identifier=cells[3]))
   finally:pa.CURRENT.reset(token);pa.DEADLINE.reset(deadline);browser.close()
   self.assertEqual(len(run.documents),1,run.visual_adapter_facts)
   self.assertEqual(len(json.loads(run.documents[0][1])),2)
   self.assertGreaterEqual(run.visual_adapter_facts[0]['total_ms'],600)
   self.assertLess(run.visual_adapter_facts[0]['total_ms'],8000)

if __name__=='__main__':unittest.main()
