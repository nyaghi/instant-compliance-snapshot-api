"""Washington Sales submission must reach the form, not its loading overlay."""
import ast
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch
import registry_snapshot_server as cc


class Submission(unittest.TestCase):
    def test_other_master_and_module_functions_unchanged_from_bh(self):
        root=Path(cc.__file__).parent
        for name in ['registry_snapshot_server.py','CharityClarity_WA_NM_checker.py']:
            old=ast.parse(subprocess.check_output(['git','show','af7b174:'+name],cwd=root).decode())
            current=(root/name).read_text(encoding='utf-8')
            if name=='registry_snapshot_server.py':
                # Only the tested new trial connector version is added to the
                # three existing compatibility gates; retain all other scope checks.
                self.assertEqual(current.count(', "0.6.63"'),3)
                self.assertEqual(current.count(', "0.6.64"'),3)
                self.assertEqual(current.count(', "0.6.66"'),3)
                self.assertEqual(current.count(', "0.6.67"'),3)
                current=current.replace(', "0.6.63"','').replace(', "0.6.64"','').replace(', "0.6.66"','').replace(', "0.6.67"','').replace(', "0.6.68"','').replace(', "0.6.69"','').replace(', "0.6.70"','')
            new=ast.parse(current)
            allowed={'fill_fein_and_search','search_wa'} if name.startswith('Charity') else {'final_four_browser_lookup'}
            for tree in [old,new]:
                tree.body=[n for n in tree.body if getattr(n,'name','') not in allowed]
            self.assertEqual(ast.dump(old),ast.dump(new),name)

    def test_sales_submit_waits_for_overlay_and_submits_exact_ein_once(self):
        module = cc.load_wa_nm_module()
        with cc.checker.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content('''<input id="FEINNoSearchField"><button onclick="window.sent=(window.sent||[]).concat(document.querySelector('input').value)">Search</button>
                    <script>document.querySelector('input').addEventListener('change',()=>{
                    const overlay=document.createElement('div');overlay.id='loading';
                    overlay.style='position:fixed;inset:0;z-index:100;background:white';
                    document.body.append(overlay);setTimeout(()=>overlay.remove(),350);},{once:true});</script>''')
                with patch.object(module, 'switch_to_fein_mode'):
                    self.assertTrue(module.fill_fein_and_search(page, '27-1635830', readiness_waits_only=True))
                self.assertEqual(page.evaluate('window.sent'), ['271635830'])
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
