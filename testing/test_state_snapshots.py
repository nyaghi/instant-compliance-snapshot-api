"""Local saved-source integration controls. Fixtures are not live state searches."""
import base64, copy, hashlib, io, json, os, socket, sys, tempfile, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import threading, urllib.request, urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deployment import state_snapshots as s
import registry_snapshot_server as c
from deployment.performance_lab import build_handler
from PIL import Image,ImageDraw
from pypdf import PdfReader
COHORT=json.loads((Path(__file__).parent/'fixtures/oct19-cohort.json').read_text())[:30]
TIMINGS=[]

def image(name,identifier):
    im=Image.new('RGB',(1000,1200),'white');d=ImageDraw.Draw(im)
    for y,t in [(30,'LOCAL TEST FIXTURE - NOT A LIVE REGISTRY CAPTURE'),(100,name),(140,identifier),(180,'Status: Registered')]:d.text((25,y),t,fill='black')
    out=io.BytesIO();im.save(out,format='PNG');return out.getvalue()

class Snapshots(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'archive.sqlite';self.store=s.SQLiteStore(self.path)
        self.p=patch.object(s,'STORE',self.store);self.p.start();self.addCleanup(self.p.stop)
        connect=socket.create_connection
        def loopback_only(address,*args,**kwargs):
            if address[0]!='127.0.0.1':raise AssertionError('No external network in local replay')
            return connect(address,*args,**kwargs)
        p=patch.object(socket,'create_connection',side_effect=loopback_only)
        p.start();self.addCleanup(p.stop)
    def asset(self,org=COHORT[0],identifier='111',run='test-run-000000000000001',state='OR'):
        return s.asset_for(image(org['name'],identifier),kind='image',state=state,ein=org['ein'],run_id=run,
            source_url='https://'+sorted(s.OFFICIAL_HOSTS[state])[0]+'/public-record',
            organization_name=org['name'],identifier=identifier,record_name=org['name'],
            capture_note='LOCAL TEST FIXTURE. This PDF does not establish any current state status.')
    def result(self,org=COHORT[0],identifier='111',state='OR'):
        return dict(organization_name=org['name'],ein=org['ein'],state=state,status='Current',success=True,
            matched_registry_name=org['name'],matched_registry_identifier=identifier,comments='Original comment')
    def test_thirty_joined_capture_worker_archive_pdf_restart_controls(self):
        for org in COHORT:
            with self.subTest(org=org['name']):
                started=time.perf_counter();asset=self.asset(org);r=self.result(org)
                # The private child file is JSON, then the supervisor archives
                # before publishing. No DB credentials are supplied to a child.
                private=json.loads(json.dumps({**r,'_worker_source_archives':[asset]}))
                job={'state':'OR','payload':{'ein':org['ein']}}
                with patch.object(s,'PostgresStore',return_value=self.store):
                    public=s.persist_worker_result(SimpleNamespace(pool=None),private,job)
                self.assertEqual(public['status'],r['status']);self.assertNotIn('_worker_source_archives',public)
                self.assertNotIn(asset['content'],json.dumps(public))
                ident=public['evidence_url'].split('/')[-1][:-4]
                # Independent process/store instance, no browser or lookup.
                with patch.object(c,'run_state_lookup',side_effect=AssertionError('PDF click must never run lookup')):
                    meta,pdf=s.saved_pdf(ident,s.SQLiteStore(self.path))
                self.assertEqual(meta['ein'],s.digits(org['ein']));self.assertEqual(meta['identifier'],'111')
                pages=PdfReader(io.BytesIO(pdf)).pages
                self.assertEqual(len(pages),1);self.assertEqual(pages[0].extract_text(),'')
                self.assertEqual(len(pages[0].images),1)
                with Image.open(io.BytesIO(pages[0].images[0].data)) as embedded, Image.open(io.BytesIO(image(org['name'],'111'))) as original:
                    self.assertEqual(embedded.convert('RGB').tobytes(),original.convert('RGB').tobytes())
                self.assertEqual(s.saved_pdf(ident,self.store)[1],pdf)
                TIMINGS.append(round((time.perf_counter()-started)*1000,3))
        self.assertEqual(len(set(s.digits(o['ein']) for o in COHORT)),30)
    def test_thirty_name_collisions_runs_and_candidate_binding(self):
        for org in COHORT:
            a=self.asset(org);b=self.asset(org,'222',run='test-run-000000000000002')
            refs=[s.archive(x,ein=org['ein'],state='OR',run_id=x['run_id']) for x in (a,b)]
            self.assertNotEqual(refs[0]['url'],refs[1]['url'])
            self.assertEqual(s.attach_links(self.result(org),refs)['evidence_url'],refs[0]['url'])
            self.assertEqual(s.attach_links(self.result(org,'222'),refs)['evidence_url'],refs[1]['url'])
            for changed in [{'ein':'999999999'},{'state':'NV'},{'matched_registry_identifier':'333'},
                            {'matched_registry_name':'Another Foundation'}]:
                self.assertEqual(s.attach_links({**self.result(org),**changed},refs)['evidence_url'],'')
            self.assertEqual(s.attach_links({**self.result(org),'matched_registry_identifier':''},refs)['evidence_url'],'')
    def test_guards_and_fail_soft_storage(self):
        a=self.asset();ein=COHORT[0]['ein'];run=a['run_id']
        for changes in [{'state':'NV'},{'ein':'999999999'},{'run_id':'other-run-000000000000000'},
                        {'source_url':'https://evil.test/'},{'source_url':'https://justice.oregon.gov/login'},
                        {'content':'!notbase64'},{'content':base64.b64encode(b'not an image').decode()},
                        {'captured_at':time.time()+1000}]:
            with self.subTest(change=list(changes)),self.assertRaises(Exception):s.validate_asset({**a,**changes},ein=ein,state='OR',run_id=run)
        self.assertNotIn('secret',s.public_url('https://justice.oregon.gov/x?token=secret&id=10','OR'))
        blank=io.BytesIO();Image.new('RGB',(400,300),'white').save(blank,format='PNG')
        with self.assertRaisesRegex(ValueError,'Blank source screenshot'):
            s.validate_asset({**a,'content':base64.b64encode(blank.getvalue()).decode()},ein=ein,state='OR',run_id=run)
        job={'state':'OR','payload':{'ein':ein}};original=self.result()
        with patch.object(s,'PostgresStore',side_effect=RuntimeError('DB unavailable')):
            out=s.persist_worker_result(SimpleNamespace(pool=None),{**original,'_worker_source_archives':[a]},job)
        self.assertEqual(out['status'],original['status']);self.assertEqual(out['evidence_url'],'')
        self.assertEqual(out['evidence_capture'],'unavailable')
    def test_capture_exact_source_context_and_missing_record(self):
        for org in COHORT:
            with s.CaptureRun(org['name'],org['ein'],'OR') as capture:
                capture.document('https://justice.oregon.gov/records',image(org['name'],'111'),'image',org['name']+' 111')
                good=capture.finish(self.result(org));self.assertEqual(len(good['_worker_source_archives']),1)
                bad=capture.finish(self.result(org,'222'));self.assertNotIn('_worker_source_archives',bad)
            self.assertIsNone(s.CURRENT.get())
        with s.CaptureRun('Other Foundation','999999999','OR') as capture:
            capture.document('https://justice.oregon.gov/records',b'Verify you are human No records found')
            r=capture.finish(dict(state='OR',ein='999999999',status='Not Registered',success=True))
            self.assertNotIn('_worker_source_archives',r)
    def test_only_original_visual_sources_can_be_published(self):
        for kind,raw in [('source_text',b'Official text'),('source_json',b'{"features":[]}')]:
            a=self.asset();a.update(kind=kind,content=base64.b64encode(raw).decode())
            with self.assertRaisesRegex(ValueError,'actual page pixels'):
                s.archive(a,ein=a['ein'],state='OR',run_id=a['run_id'])
            with self.assertRaises(ValueError):s.render_pdf({'kind':kind},raw)
            meta={'kind':kind,'source_sha256':hashlib.sha256(raw).hexdigest()}
            # A stale pre-change cache cannot expose a reconstructed PDF.
            stale=SimpleNamespace(load=lambda _: (meta,raw,b'%PDF-old-reconstruction'))
            with self.assertRaisesRegex(ValueError,'original visual'):s.saved_pdf('a'*64,stale)
        from reportlab.pdfgen import canvas
        raw=io.BytesIO();pdf=canvas.Canvas(raw);pdf.drawString(20,700,'ORIGINAL STATE DOCUMENT TEST');pdf.showPage();pdf.save()
        source=raw.getvalue();a=self.asset();a.update(kind='source_pdf',content=base64.b64encode(source).decode())
        ref=s.archive(a,ein=a['ein'],state='OR',run_id=a['run_id'])
        _,saved=s.saved_pdf(ref['url'].split('/')[-1][:-4],self.store)
        self.assertEqual(saved,source)
        self.assertEqual(len(PdfReader(io.BytesIO(saved)).pages),1)

    def test_corrupted_source_never_generates_pdf(self):
        a=self.asset();ref=s.archive(a,ein=a['ein'],state='OR',run_id=a['run_id']);ident=ref['url'].split('/')[-1][:-4]
        meta,raw,_=self.store.load(ident)
        fake=SimpleNamespace(load=lambda _: (meta,raw+b'changed',None))
        with self.assertRaisesRegex(ValueError,'integrity'):s.saved_pdf(ident,fake)
    def test_thirty_signed_identity_actions_keep_exact_record_archive(self):
        for org in COHORT:
            with self.subTest(org=org['name']),patch.object(c,'trial_identity',return_value={'origin':'https://fixture.onrender.com'}),patch.object(c,'APP_VERSION','local-snapshot-staging'),patch.object(c,'NY_CONNECTOR_SIGNING_KEY','local-only-not-real-'*4):
                a=self.asset(org,state='NC');b=self.asset(org,'222',state='NC')
                refs=[s.archive(x,ein=org['ein'],state='NC',run_id=x['run_id']) for x in (a,b)]
                rows=[dict(name=org['name'],identifier=i,ein=org['ein'],location='Boston, MA',url='https://www.sosnc.gov/record/'+i,
                    raw_status='Active',status='Current',expiration='12/31/2027',_identity_outcome='possible') for i in ['111','222']]
                data={**self.result(org,state='NC'),'status':'Needs Review','matched_registry_name':'','matched_registry_identifier':'',
                    'email':'test@compliance-express.com','device_id':'local-device'}
                token=s.REFERENCES.set(refs)
                try:c.attach_identity_review(data,dict(records=rows,exclusive=True,search_complete=True))
                finally:s.REFERENCES.reset(token)
                self.assertEqual([r['evidence_url'] for r in data['identity_review']['candidates']],[r['url'] for r in refs])
                candidate=data['identity_review']['candidates'][1]
                payload=dict(token=data['identity_review']['token'],ein=data['ein'],state='NC',candidate_id=candidate['id'],action='accept')
                out=c.resolve_identity_review(payload,'test@compliance-express.com','local-device')
                self.assertEqual(out['matched_registry_identifier'],'222');self.assertEqual(out['evidence_url'],refs[1]['url'])
                payload.update(token=out['identity_review']['token'],action='clear')
                out=c.resolve_identity_review(payload,'test@compliance-express.com','local-device')
                self.assertEqual(out['evidence_url'],'')
    def test_thirty_inline_continuations_keep_signed_owner_and_exact_capture(self):
        for org in COHORT:
            with self.subTest(org=org['name']),patch.object(c,'trial_identity',return_value={'origin':'https://fixture.onrender.com'}),patch.object(c,'APP_VERSION','local-snapshot-staging'),patch.object(c,'NY_CONNECTOR_SIGNING_KEY','local-only-not-real-'*4):
                data={**self.result(org,state='NC'),'status':'Needs Review','matched_registry_name':'','matched_registry_identifier':'',
                    'email':'test@compliance-express.com','device_id':'local-device'}
                row=dict(name=org['name'],identifier='111',ein=org['ein'],location='Boston, MA',url='https://www.sosnc.gov/record/111',
                    raw_status='Active',status='Current',expiration='12/31/2027',_identity_outcome='possible')
                c.attach_identity_review(data,dict(records=[row],exclusive=True,search_complete=True))
                before=c.identity_review_unpack(data['identity_review']['token'],'test@compliance-express.com','local-device')
                before['owner']=['test@compliance-express.com','local-device']
                data['identity_review']=c.identity_review_view(before)
                asset=self.asset(org,state='NC');data['_worker_source_archives']=[asset]
                out=s.persist_inline_result(c,data)
                self.assertNotIn('_worker_source_archives',out);self.assertNotIn(asset['content'],json.dumps(out))
                candidate=out['identity_review']['candidates'][0];self.assertTrue(candidate['evidence_url'])
                after=c.identity_review_unpack(out['identity_review']['token'],'test@compliance-express.com','local-device')
                for field in ['owner','issued','expires','history','decisions']:
                    self.assertEqual(after[field],before[field])
                self.assertEqual(after['records'][0]['evidence_url'],candidate['evidence_url'])
                with self.assertRaises(ValueError):c.identity_review_unpack(out['identity_review']['token'],'foreign@invalid.test','foreign-device')
                with patch.object(s,'STORE',None):
                    missing=s.persist_inline_result(c,data)
                    self.assertNotIn('_worker_source_archives',missing);self.assertEqual(missing['status'],data['status'])

    def test_thirty_wi_and_ky_fresh_decisions_keep_new_record_snapshot(self):
        for org in COHORT:
            for state,action,new_id in [('WI','reject','222'),('KY','accept','111')]:
                with self.subTest(org=org['name'],state=state),patch.object(c,'trial_identity',return_value={'origin':'https://fixture.onrender.com'}),patch.object(c,'APP_VERSION','local-snapshot-staging'),patch.object(c,'NY_CONNECTOR_SIGNING_KEY','local-only-not-real-'*4):
                    old=self.asset(org,state=state);fresh=self.asset(org,new_id,state=state,run='fresh-lookup-00000000000001')
                    refs=[s.archive(a,ein=org['ein'],state=state,run_id=a['run_id']) for a in [old,fresh]]
                    data={**self.result(org,state=state),'status':'Needs Review','matched_registry_name':'','matched_registry_identifier':'',
                        'email':'test@compliance-express.com','device_id':'local-device','evidence_url':refs[0]['url']}
                    row=dict(name=org['name'],identifier='111',ein=org['ein'],location='Boston, MA',url='https://'+sorted(s.OFFICIAL_HOSTS[state])[0]+'/record/111',
                        raw_status='Active',status='Current',expiration='12/31/2027',_identity_outcome='possible',evidence_url=refs[0]['url'])
                    c.attach_identity_review(data,dict(records=[row],exclusive=True,search_complete=False))
                    candidate=data['identity_review']['candidates'][0]
                    fresh_result={**self.result(org,new_id,state),'evidence_url':refs[1]['url']}
                    with patch.object(c,'run_state_lookup',return_value=fresh_result) as lookup:
                        out=c.resolve_identity_review(dict(token=data['identity_review']['token'],ein=org['ein'],state=state,
                            candidate_id=candidate['id'],action=action),'test@compliance-express.com','local-device')
                    lookup.assert_called_once();self.assertEqual(out['evidence_url'],refs[1]['url'])
                    self.assertEqual(out['matched_registry_identifier'],new_id)

    def test_all_38_state_archive_bindings(self):
        for state in s.OFFICIAL_HOSTS:
            with self.subTest(state=state):
                asset=self.asset(state=state);ref=s.archive(asset,ein=asset['ein'],state=state,run_id=asset['run_id'])
                self.assertEqual(s.attach_links(self.result(state=state),[ref])['evidence_url'],ref['url'])
        self.assertEqual(len(s.OFFICIAL_HOSTS),38)
        for state,url in c.NAME_SEARCH_PREFLIGHT_URLS.items():
            if state in s.OFFICIAL_HOSTS:self.assertTrue(s.public_url(url,state))
        self.assertTrue(s.public_url(c.RI_PUBLIC_SEARCH_API,'RI'))
        with self.assertRaises(ValueError):s.public_url('https://r.jina.ai/https://apps.dfi.wi.gov/','WI')
    def test_ny_same_ein_same_name_uses_selected_organization_id_link(self):
        org=COHORT[0]
        refs=[]
        for ident in ['45-54-08','47-32-27']:
            asset=self.asset(org,identifier=ident,state='NY')
            refs.append(s.archive(asset,ein=org['ein'],state='NY',run_id=asset['run_id']))
        for index,ident in enumerate(['45-54-08','47-32-27']):
            r={**self.result(org,identifier=s.digits(org['ein']),state='NY'),
               'source_url':'https://charities-search.ag.ny.gov/RegistrySearch/'+ident}
            self.assertEqual(s.attach_links(r,refs)['evidence_url'],refs[index]['url'])
    def test_near_deadline_skips_capture_and_preserves_body_result(self):
        with s.CaptureRun('Local Foundation','123456789','OR') as run,s.task_deadline({'_deadline_monotonic':time.monotonic()+1}):
            page=SimpleNamespace(url='https://justice.oregon.gov/record',inner_text=lambda *a,**kw: (_ for _ in ()).throw(AssertionError('No capture near deadline')))
            run.page(page)
            self.assertEqual(run.documents,[])
        self.assertEqual(s.DEADLINE.get(),float('inf'))
    def test_candidate_connector_version_accepted_only_by_existing_trial_guard(self):
        origin=c.NY_CONNECTOR_ORIGIN;org=COHORT[0]
        for state in ['NY','IL','GA']:
            with self.subTest(state=state),patch.object(c,'trial_identity',return_value={'origin':origin}),patch.object(c,'is_verified_internal_passcode',return_value=True),patch.object(c,'NY_CONNECTOR_SIGNING_KEY','local-only-key-'*5),patch.object(c,'ny_connector_advance',return_value={'phase':'complete','result':self.result(org,state=state)}):
                payload=dict(action='start',state=state,organization_name=org['name'],ein=org['ein'],connector_version='0.6.135',email='local@compliance-express.com',admin_passcode='fixture',device_id='local-device')
                code,response=c.ny_connector_request(payload,origin)
                self.assertEqual(code,200,response);self.assertEqual(response['phase'],'complete')
            with patch.object(c,'trial_identity',return_value=None),patch.object(c,'is_verified_internal_passcode',return_value=True),patch.object(c,'NY_CONNECTOR_SIGNING_KEY','local-only-key-'*5):
                code,response=c.ny_connector_request(payload,origin)
                self.assertEqual(code,400,response)
    def test_data_feed_alone_is_never_published_as_page_evidence(self):
        for org in COHORT:
            with s.CaptureRun(org['name'],org['ein'],'DC') as run:
                run.document('https://maps2.dcgis.dc.gov/registry',b'{"features":[]}',kind='source_json')
                result=run.finish(dict(ein=org['ein'],state='DC',status='Not Registered',success=True))
                self.assertNotIn('_worker_source_archives',result)
                self.assertEqual(result['evidence_capture'],'unavailable')

    def test_browser_capture_does_not_inspect_foreign_contexts_or_capture_twice(self):
        calls=[]
        class Context:
            pages=['owned-page']
            def close(self):calls.append('close-context')
        class Browser:
            @property
            def contexts(self):raise AssertionError('Foreign contexts must never be inspected')
            def new_context(self):return Context()
            def close(self):calls.append('close-browser')
        with s.CaptureRun('Fixture','123456789','OR') as run,patch.object(run,'page',side_effect=lambda p:calls.append(p)):
            wrapped=s.BrowserCaptureProxy(Browser());context=wrapped.new_context()
            context.close();wrapped.close()
        self.assertEqual(calls,['owned-page','close-context','close-browser'])

    def test_backend_capture_bounds_and_source_stability_never_break_close(self):
        for org in COHORT:
            for guard in ['oversized','changed-text','changed-url']:
                texts=[org['name']+' 111',org['name']+' 111' if guard!='changed-text' else 'Other Foundation 222']
                page=SimpleNamespace(url='https://justice.oregon.gov/record/111')
                page.inner_text=lambda *a,**kw:texts.pop(0)
                page.locator=lambda _:SimpleNamespace(evaluate=lambda *a,**kw:{'width':1000,'height':50000 if guard=='oversized' else 1200})
                def screenshot(**kwargs):
                    if guard=='oversized':raise AssertionError('Do not capture oversized page')
                    if guard=='changed-url':page.url='https://justice.oregon.gov/record/222'
                    return image(org['name'],'111')
                page.screenshot=screenshot
                with s.CaptureRun(org['name'],org['ein'],'OR') as run:
                    run.page(page);self.assertEqual(run.documents,[])
                    self.assertEqual(run.finish(self.result(org))['evidence_capture'],'unavailable')
        class BrokenContext:
            @property
            def pages(self):raise RuntimeError('Page went away')
            def close(self):return 'original-close-still-executed'
        with s.CaptureRun('Fixture','123456789','OR'):
            self.assertEqual(s.ContextCaptureProxy(BrokenContext()).close(),'original-close-still-executed')

    def test_thirty_jpeg_captures_keep_decoded_pixels_and_full_page_ratio(self):
        for org in COHORT:
            source=Image.open(io.BytesIO(image(org['name'],'111')));raw=io.BytesIO();source.save(raw,format='JPEG',quality=75)
            asset=self.asset(org);asset['content']=base64.b64encode(raw.getvalue()).decode()
            meta,original=s.validate_asset(asset,ein=org['ein'],state='OR',run_id=asset['run_id'])
            pdf=PdfReader(io.BytesIO(s.render_pdf(meta,original)));page=pdf.pages[0]
            # pypdf's high-level image exporter re-encodes JPEGs. Inspect the
            # embedded DCT stream directly to verify the actual PDF bytes.
            objects=page['/Resources']['/XObject']
            stream=next(value.get_object() for value in objects.values())
            self.assertIn('/DCTDecode',stream['/Filter'])
            self.assertEqual(stream.get_data(),original)
            self.assertAlmostEqual(float(page.mediabox.height)/float(page.mediabox.width),1200/1000)
            self.assertEqual(page.extract_text(),'')

    def test_postgres_store_contract_with_real_psycopg_json_adapter(self):
        # SQL/pool contract only; this is not a live Postgres database test.
        from contextlib import contextmanager
        class Connection:
            rows={};result=None
            def execute(self,sql,args=()):
                if sql.startswith('INSERT'):self.rows[args[0]]={'metadata':args[1].obj,'source':args[2],'pdf':None}
                elif sql.startswith('SELECT'):self.result=self.rows.get(args[0])
                elif sql.startswith('UPDATE'):self.rows[args[1]]['pdf']=args[0]
                elif not sql.startswith('SET LOCAL'):raise AssertionError(sql)
                return self
            def fetchone(self):return self.result
        class Pool:
            conn=Connection()
            @contextmanager
            def connection(self,**kwargs):yield self.conn
        store=s.PostgresStore(Pool());asset=self.asset()
        ref=s.archive(asset,ein=asset['ein'],state='OR',run_id=asset['run_id'],store=store)
        meta,pdf=s.saved_pdf(ref['url'].split('/')[-1][:-4],store)
        self.assertEqual(meta['identifier'],'111');self.assertTrue(pdf.startswith(b'%PDF-'))
    def test_optional_archive_references_cannot_exhaust_existing_signing_limits(self):
        with patch.object(c,'NY_CONNECTOR_SIGNING_KEY','local-not-real-key-'*5):
            record={'original_evidence':'x'*220000,'source_snapshots':[{'url':'x'*30000}]}
            signed=c.ny_connector_pack(record);self.assertLessEqual(len(signed),320065)
            self.assertNotIn('source_snapshots',record)
            rows=[{'identifier':str(i),'evidence_url':'/state-snapshots/'+'a'*64+'.pdf'} for i in range(100)]
            review={'base':{},'records':rows,'original_evidence':'x'*180000}
            token=c.identity_review_pack(review);self.assertLessEqual(len(token),250065)
            self.assertEqual(len(review['records']),100)
            with self.assertRaises(ValueError):c.ny_connector_pack({'original_evidence':'x'*300000})
            with self.assertRaises(ValueError):c.identity_review_pack({'original_evidence':'x'*200000})
    def test_http_route_requires_existing_private_auth_and_never_looks_up(self):
        # Local loopback only; no state or staging HTTP requests.
        a=self.asset();ref=s.archive(a,ein=a['ein'],state='OR',run_id=a['run_id'])
        handler=build_handler(c,'local-secret-not-a-real-credential')
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        import http.client
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port)
        conn.request('GET',ref['url']);r=conn.getresponse();r.read();self.assertEqual(r.status,401)
        auth='Basic '+base64.b64encode(b'lab:local-secret-not-a-real-credential').decode()
        with patch.object(c,'run_state_lookup',side_effect=AssertionError('No lookup on PDF GET')):
            conn.request('GET',ref['url'],headers={'Authorization':auth});r=conn.getresponse();pdf=r.read()
            self.assertEqual(r.status,200);self.assertEqual(r.getheader('Content-Type'),'application/pdf');self.assertTrue(pdf.startswith(b'%PDF-'))
            for path in ['/state-snapshots/../private.pdf','/state-snapshots/'+'0'*64+'.pdf']:
                conn.request('GET',path,headers={'Authorization':auth});r=conn.getresponse();r.read();self.assertEqual(r.status,404)
        conn.close()

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Snapshots)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'organizations':30,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
        'joined_archive_pdf_ms':{'mean':sum(TIMINGS)/len(TIMINGS),'max':max(TIMINGS)} if TIMINGS else {},
        'scope':'Local retained identities with modeled source images/DOM/storage; not live registry or speed validation.'}
    (Path(__file__).resolve().parents[2]/'snapshot-local-results.json').write_text(json.dumps(report,indent=2))
    sys.exit(not result.wasSuccessful())
