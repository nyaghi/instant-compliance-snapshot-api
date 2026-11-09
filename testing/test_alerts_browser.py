"""Exercise the real Alerts page in a clean Chromium context."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


class LocalHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if urlsplit(self.path).path in {'/alerts','/alerts/'}:
            self.path='/alerts.html'
        elif self.path=='/head-start/compliance-express-logo.png':
            data=(ROOT/'deployment/insight/head-start/compliance-express-logo.png').read_bytes()
            self.send_response(200);self.send_header('Content-Type','image/png');self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def log_message(self, *_):
        pass


class AlertsBrowser(unittest.TestCase):
    def test_ui_badge_history_add_and_excel(self):
        with ThreadingHTTPServer(('127.0.0.1',0),partial(LocalHandler,directory=ROOT/'web-staging')) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                with sync_playwright() as p:
                    browser=p.chromium.launch(channel='chrome',headless=True)
                    page=browser.new_page(viewport={'width':1100,'height':850},accept_downloads=True)
                    errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    origin='http://127.0.0.1:'+str(server.server_address[1])
                    model={'organizations':[],'changes':[],'failures':[],'unseen':0,'states':38,'next':None}
                    def api(route):
                        path=urlsplit(route.request.url).path
                        if path.endswith('/organizations'):
                            row=route.request.post_data_json
                            model['organizations'].append({'name':row['name'],'ein':row['ein'].replace('-',''),
                                                           'confirmed':0,'last_checked':None})
                            value={'added':True}
                        elif path.endswith('/seen'):
                            item=next(x for x in model['changes'] if x['id']==route.request.post_data_json['id'])
                            item['seen']=1794230300
                            model['unseen']=sum(not x['seen'] for x in model['changes'])
                            value={'unseen':model['unseen']}
                        else:value=model
                        route.fulfill(json=value)
                    page.route('**/api/alerts**',api)
                    page.goto(origin+'/alerts/')
                    page.get_by_text('No status changes to review.').wait_for()
                    self.assertTrue(page.locator('.cc-alert-count').is_hidden())
                    page.get_by_role('button',name='Add Organization').click()
                    page.get_by_label('Organization name').fill('Example & Charity')
                    page.get_by_label('EIN').fill('01-2345678')
                    page.get_by_role('button',name='Save organization').click()
                    page.get_by_text('0 / 38 states confirmed').wait_for()
                    self.assertEqual(len(model['organizations']),1)
                    model['changes']=[
                        {'id':3,'name':'Example & Charity','ein':'012345678','state':'CO','previous':'Upcoming Filing',
                         'status':'Current','direction':'favorable','checked':1794230000,'seen':None},
                        {'id':2,'name':'Example & Charity','ein':'012345678','state':'NY','previous':'Current',
                         'status':'Delinquent','direction':'adverse','checked':1794230000,'seen':None},
                    ]
                    model['unseen']=2
                    page.reload()
                    page.get_by_role('link',name='CharityClarity Alerts, 2 new').wait_for()
                    self.assertEqual(page.locator('#changes h3').all_text_contents(),['Needs attention','Favorable changes'])
                    page.get_by_role('button',name='Mark Example & Charity NY change seen').click()
                    page.get_by_role('link',name='CharityClarity Alerts, 1 new').wait_for()
                    self.assertEqual(page.get_by_text('Seen',exact=True).count(),1)
                    with page.expect_download() as download:
                        page.get_by_role('button',name='Download Excel').click()
                    self.assertEqual(download.value.suggested_filename,'CharityClarity-Alerts.xlsx')
                    with ZipFile(download.value.path()) as z:
                        body=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
                        relations=ET.fromstring(z.read('xl/worksheets/_rels/sheet1.xml.rels'))
                        self.assertEqual(len(body.findall('.//{*}row')),3)
                        self.assertIn('Example & Charity',''.join(body.itertext()))
                        self.assertEqual({r.get('Target') for r in relations},
                                         {origin+'/api/alerts/evidence/2',origin+'/api/alerts/evidence/3'})
                    self.assertEqual(model['unseen'],1)
                    page.set_viewport_size({'width':390,'height':844})
                    page.goto(origin+'/alerts/?example=1')
                    page.get_by_text('Example data for the demo.',exact=False).wait_for()
                    page.get_by_role('link',name='CharityClarity Alerts, 3 new').wait_for()
                    self.assertEqual(errors,[])
                    browser.close()
            finally:server.shutdown()
