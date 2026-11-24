"""Exercise California's tabbed candidate detail with an intercepted local browser."""
import html
import json
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright
from deployment.source_visual_adapters import ca_tabbed_exempt_demographics, ca_tabbed_exempt_ids


class CaliforniaExemptTabs(unittest.TestCase):
    def test_70_recorded_organizations(self):
        roster=json.loads((Path(__file__).parent/'fixtures/gate55/LOCAL-70.json').read_text())
        self.assertEqual(len({o['ein'] for o in roster}),70)
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page()
            url='https://ca-rcf.evokeplatform.com/app/publicPortal/entityDetails/6632288'
            page.route('**/*',lambda route:route.fulfill(content_type='text/html',body='<html></html>'))
            page.goto(url)
            for o in roster:
                ein=o['ein'].replace('-','')
                name=o['name']
                src='\n'.join(['Entity Detail','Entity IDs','Entity Type','Business','Entity Status','Exempt','Entity Name',name,'DBA','Out of State?','Yes'])
                self.assertIsNotNone(ca_tabbed_exempt_demographics(src,name,'Exempt'))
                for bad in [src.replace('Entity Status\nExempt','Entity Status\nCurrent'),src+'\nEntity Name',src.replace(name,'Unrelated Foundation'),src+'\nAccess denied']:
                    self.assertIsNone(ca_tabbed_exempt_demographics(bad,name,'Exempt'))
                for label,number,value,expected,ok in [('FEIN','6632288','', '',True),('FEIN','6632288',ein,ein,True),('FEIN','6632288',ein,'',False),('FEIN','6632289','', '',False),('Different field','6632288','', '',False)]:
                    page.set_content(f"""<button role="tab" onclick="details.hidden=true">Demographics</button>
<button role="tab" onclick="details.hidden=false">Entity IDs</button><div id="details" role="tabpanel" hidden>
<div class="formio-component-entityId">Entity Id<p>{number}</p></div>
<div class="formio-component-fein">{label}<p>{html.escape(value)}</p></div></div>""")
                    self.assertEqual(ca_tabbed_exempt_ids(page,url,'6632288',expected,lambda:3000),ok,name)
                    self.assertTrue(page.locator('#details').is_hidden())
            browser.close()


if __name__=='__main__': unittest.main()
