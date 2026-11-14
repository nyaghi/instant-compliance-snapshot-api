"""Use Chromium to verify that the Illinois public close control is safe to reuse."""
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright

CONTENT = (Path(__file__).resolve().parents[1] / "deployment/staging_connector/registry-content.js").read_text()


class IllinoisDetailDialog(unittest.TestCase):
    def test_only_the_public_close_control_is_used(self):
        instrumented = CONTENT.replace("  async function illinois(query", "  window.testReturn = ilReturnToSearch;\n  async function illinois(query", 1)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.route("https://charitable.illinoisattorneygeneral.gov/search", lambda route: route.fulfill(
                content_type="text/html", body="""
                <section><button aria-label=Close>Close</button>
                <div id=KendoWindowLevel1>CO Number: 10000000</div></section>
                <table id=results><tbody><tr><td>10000001</td></tr></tbody></table>
                <script>
                let closes=0;
                document.querySelector('button').onclick=()=>{
                  closes++;
                  document.querySelector('#KendoWindowLevel1').style.display='none';
                };
                window.chrome={runtime:{onMessage:{addListener(){}}}};
                </script>"""))
            page.goto("https://charitable.illinoisattorneygeneral.gov/search")
            page.add_script_tag(content=instrumented)
            page.evaluate("window.testReturn()")
            self.assertEqual(page.evaluate("closes"), 1)
            self.assertEqual(page.locator("#results").inner_text(), "10000001")
            page.evaluate("window.testReturn()")
            self.assertEqual(page.evaluate("closes"), 1)
            page.locator("#KendoWindowLevel1").evaluate("(node) => node.style.display = 'block'")
            page.get_by_role("button", name="Close").evaluate("(node) => node.remove()")
            self.assertEqual(page.evaluate("window.testReturn().catch(error => error.message)"),
                             "NY_CONNECTOR_IL_DETAIL_NOT_CLOSED")
            browser.close()


if __name__ == "__main__":
    unittest.main()
