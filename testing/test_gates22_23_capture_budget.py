"""Joined offline capture/archive and elapsed-budget controls; no live queries."""
import copy,hashlib,io,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PIL import Image,ImageDraw
from pypdf import PdfReader
import registry_snapshot_server as m
from deployment import state_snapshots as s,ma_withheld_evidence as ma,nd_consensus_evidence as nd
from deployment import source_visual_adapters as visual

def fixture_image(label):
    out=io.BytesIO();im=Image.new('RGB',(800,600),'white')
    ImageDraw.Draw(im).text((20,20),'OFFLINE TEST FIXTURE\n'+label,fill='black')
    im.save(out,format='PNG');return out.getvalue()

class CaptureBinding(unittest.TestCase):
    def test_ri_same_name_candidates_keep_separate_original_ids(self):
        run=s.CaptureRun('Example Center','123456789','RI')
        rows=[{'name':'Example Center','identifier':'CO.12345','status':'Pending','raw_status':'ACTIVE PENDING RENEWAL','url':'https://ridbrprod-search.state-reg-eastern.tylerapp.com/search/C12345/detail'},
              {'name':'Example Center','identifier':'CO.67890','status':'Closed / Withdrawn / Canceled','raw_status':'INACTIVE','url':'https://ridbrprod-search.state-reg-eastern.tylerapp.com/search/C67890/detail'}]
        for row in rows:row['_identity_outcome']='possible';row['ein']=''
        result={'state':'RI','ein':run.ein,'organization_name':run.name,'status':'Unable to Confirm','success':False,
                'comments':'Confirm which original registry record belongs to the entered organization.',
                '_worker_identity_review':{'records':rows,'search_complete':True}}
        captures=[]
        def photograph(master,candidate,target,deadline):
            captures.append((candidate['matched_registry_identifier'],deadline))
            text=candidate['matched_registry_name']+' '+candidate['matched_registry_identifier']+' '+candidate['raw_status_text']
            target.document(candidate['source_url'],fixture_image(text),'image',text)
        with patch.object(visual,'capture_selected_source',side_effect=photograph):
            visual.capture_result_visuals(m,result,run,time.monotonic()+60)
        self.assertEqual([x[0] for x in captures],['CO.12345','CO.67890'])
        self.assertEqual(captures[0][1],captures[1][1])
        assets=run.finish(result)['_worker_source_archives']
        self.assertEqual({a['identifier'] for a in assets},{'CO.12345','CO.67890'})
        for asset in assets:
            self.assertIn(asset['identifier'],asset['public_text'])
            self.assertNotIn('CO.67890' if asset['identifier']=='CO.12345' else 'CO.12345',asset['public_text'])
        from deployment import identity_evidence
        with tempfile.TemporaryDirectory() as folder:
            store=s.SQLiteStore(Path(folder)/'ri.sqlite')
            with patch.object(s,'STORE',store),patch.object(m,'APP_VERSION','fixture-staging'), \
                 patch.object(m,'trial_identity',return_value=False),patch.object(m,'NY_CONNECTOR_SIGNING_KEY','offline-fixture-signing-key-'*3):
                data=s.persist_worker_result(None,run.finish(result),{'state':'RI','payload':{'ein':run.ein}},store=store)
                m.attach_identity_review(data,data['_worker_identity_review'])
                data=identity_evidence.bind(m,data)
                cards=data['identity_review']['candidates']
                self.assertEqual(len({x['evidence_url'] for x in cards}),2)
                self.assertTrue(all(x['evidence_url'].startswith('/state-snapshots/') for x in cards))
                def decide(current,index,action):
                    return m.resolve_identity_review({'token':current['identity_review']['token'],'ein':run.ein,
                        'state':'RI','candidate_id':cards[index]['id'],'action':action},'qa@example.test','fixture-device')
                accepted=decide(data,0,'accept')
                selected=decide(accepted,1,'reject')
                self.assertEqual(selected['status'],'Pending')
                self.assertEqual(selected['evidence_url'],cards[0]['evidence_url'])
                rejected=decide(selected,0,'reject')
                self.assertEqual(rejected['status'],'Not Registered')
                self.assertNotEqual(rejected.get('evidence_url'),cards[0]['evidence_url'])
                self.assertNotEqual(rejected.get('evidence_url'),cards[1]['evidence_url'])
                undone=decide(selected,0,'clear')
                self.assertNotEqual(undone.get('evidence_url'),cards[0]['evidence_url'])
    def persist(self,run,row):
        private=run.finish(row)
        self.assertTrue(private.get('_worker_source_archives'))
        with tempfile.TemporaryDirectory() as folder:
            store=s.SQLiteStore(Path(folder)/'archive.sqlite')
            with patch.object(s,'PostgresStore',return_value=store):
                public=s.persist_worker_result(SimpleNamespace(pool=None),private,{'state':run.state,'payload':{'ein':run.ein}})
            self.assertTrue(public.get('evidence_url'),public.get('evidence_capture'))
            key=public['evidence_url'].split('/')[-1][:-4]
            meta,pdf=s.saved_pdf(key,store)
            self.assertEqual(meta['ein'],run.ein)
            self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages),1)
        return private

    def test_ma_withheld_original_survives_archive_without_status_fabrication(self):
        run=s.CaptureRun('Example Hospital','123456789','MA')
        candidate={'value':'a094U00001vhxgtQAA','label':'EXAMPLE HOSPITAL'}
        body='EXAMPLE HOSPITAL '+ma.MESSAGE
        raw=fixture_image(body)
        page=Mock(url=ma.URL)
        page.evaluate.side_effect=lambda *a:{'bound':True,'source_text':body}
        def photograph(p):run.document(ma.URL,raw,'image',body)
        with patch.object(run,'page',side_effect=photograph):
            self.assertTrue(ma.capture(page,run,candidate,run.ein))
        row={'state':'MA','ein':run.ein,'organization_name':run.name,'status':'Unable to Confirm','success':True,
             'status_reason':ma.REASON,'matched_registry_identifier':candidate['value'],'matched_registry_name':candidate['label']}
        private=self.persist(run,row)
        self.assertEqual(private['status'],'Unable to Confirm')
        for changed in [{'matched_registry_identifier':'a094U00001vhxguQAA'}, {'matched_registry_name':'OTHER HOSPITAL'},
                        {'status':'Current'},{'status_reason':'OTHER'}]:
            self.assertFalse(ma.bound(run,{**row,**changed},run.documents[0]))
        run.ma_withheld_bindings={}
        self.assertFalse(run.finish(row).get('_worker_source_archives'))

    def test_nd_consensus_binds_all_ids_and_refuses_changed_page(self):
        records=[{'RECORD_NUM':'0000012345','TITLE':['Example Foundation'],'STATUS':'Inactive'},
                 {'RECORD_NUM':'0000012346','TITLE':['Example Foundation'],'STATUS':'Inactive - Voluntary'}]
        result=SimpleNamespace(status_reason='ND_MATCHING_RECORDS_INACTIVE',matched_registry_name='Example Foundation',
            matched_registry_identifier='0000012345, 0000012346',raw_status_text='0000012345: Inactive; 0000012346: Inactive - Voluntary')
        row={'state':'ND','ein':'123456789','organization_name':'Example Foundation','status':'Closed / Withdrawn / Canceled',
             'success':True,**vars(result)}
        for changed in [False,True]:
            with self.subTest(changed=changed):
                run=s.CaptureRun(row['organization_name'],row['ein'],'ND');token=s.CURRENT.set(run)
                self.addCleanup(s.CURRENT.reset,token)
                page=Mock(url=nd.URL);page.evaluate.side_effect=[records,None if changed else records]
                page.inner_text.return_value='Example Foundation '+result.raw_status_text
                page.screenshot.return_value=fixture_image(page.inner_text.return_value)
                nd.capture(page,records,result,time.perf_counter()+20)
                if changed:self.assertFalse(run.finish(row).get('_worker_source_archives'));continue
                self.persist(run,row)
                for modification in [{'matched_registry_identifier':'0000012345'},{'raw_status_text':'Active'},{'status':'Current'}]:
                    self.assertFalse(nd.image_bound(run,{**row,**modification},nd.URL,page.screenshot.return_value,'image'))

class Budgets(unittest.TestCase):
    def setUp(self):self.org=SimpleNamespace(organization_name='Example Foundation',ein='123456789')
    def test_wi_missing_form_cannot_spend_two_fresh_default_selector_timeouts(self):
        clock=[100.0];page=Mock();primary=Mock();fallback=Mock()
        page.locator.side_effect=lambda selector: primary if selector=='#ctl00_cphMainContent_ddlProfesionalList' else fallback
        page.goto.side_effect=lambda *a,**kw: clock.__setitem__(0,104.0)
        def missing(**kw):
            self.assertEqual(kw['timeout'],1000)
            clock[0]+=kw['timeout']/1000
            raise TimeoutError('source does not expose the search form')
        primary.select_option.side_effect=missing
        progress={'attempted':[],'completed':set(),'deadline':105.0}
        with patch.object(m.time,'perf_counter',side_effect=lambda:clock[0]), \
             patch.object(m,'wi_http_search_best_match',return_value=(None,False)), \
             patch.object(m,'wi_reader_search_best_match',return_value=(None,False)), \
             patch.object(m.checker,'safe_wait_for_network_idle'),patch.object(m,'WI_BROWSER_VARIANT_LIMIT',1):
            result=m.search_wi(page,self.org,progress=progress)
        self.assertFalse(result.success);self.assertNotEqual(result.status,'Not Registered')
        primary.select_option.assert_called_once();fallback.first.select_option.assert_not_called()
        self.assertEqual(clock[0],105.0)

    def test_wi_direct_request_timeout_uses_only_remaining_allowance(self):
        clock=[100.0];opener=Mock();reply=Mock()
        reply.__enter__=Mock(return_value=reply);reply.__exit__=Mock(return_value=False)
        def read():clock[0]=101.0;return b'<html>source unavailable</html>'
        reply.read.side_effect=read;opener.open.return_value=reply
        with patch.object(m.time,'perf_counter',side_effect=lambda:clock[0]),patch.object(m,'wi_request_opener',return_value=opener):
            result=m.wi_http_search_best_match(['Example Foundation'],['Example Foundation'],101.0)
        self.assertEqual(result,(None,False));opener.open.assert_called_once()
        self.assertEqual(opener.open.call_args.kwargs['timeout'],1.0)

    def test_expired_wi_budget_never_starts_source_or_new_lane(self):
        progress={'attempted':[],'completed':set(),'deadline':time.perf_counter()-1}
        with patch.object(m,'wi_http_search_best_match') as http,patch.object(m,'WI_BACKEND_BROWSER_SEMAPHORE') as lane,patch.object(m,'WI_SIDECAR_SEMAPHORE') as side:
            self.assertEqual(m.search_wi(None,self.org,progress=progress).status,'Site Not Reachable')
            self.assertEqual(m.search_wi_backend_browser_fallback(self.org,progress=progress).status,'Site Not Reachable')
            self.assertEqual(m.search_wi_sidecar(self.org,deadline=progress['deadline']).status,'Site Not Reachable')
            http.assert_not_called();lane.acquire.assert_not_called();side.acquire.assert_not_called()
    def test_wi_semantic_retry_cannot_reset_consumed_allowance(self):
        def source(name,ein,state,**kw):
            kw['wi_progress']['deadline']=time.perf_counter()-1
            return {'state':state,'status':'Site Not Reachable','success':False,'ein':ein,'organization_name':name}
        with patch.object(m,'run_state_lookup',side_effect=source) as lookup,patch.object(m,'SINGLE_STATE_SEMANTIC_RETRY_STATES',{'WI'}),patch.object(m,'SINGLE_STATE_SEMANTIC_RETRY_ATTEMPTS',3),patch.object(m,'SINGLE_STATE_SEMANTIC_RETRY_DELAY_SECONDS',0):
            result=m._run_single_state_lookup_reliably_source(self.org.organization_name,self.org.ein,'WI')
        self.assertEqual(lookup.call_count,1);self.assertEqual(result['semantic_attempts'],1)
    def test_dc_one_fresh_recovery_and_unchanged_other_state_policy(self):
        deadline=time.monotonic()+75
        with patch.object(m,'identity_fetch',side_effect=[TimeoutError('first'),'{}']) as fetch,patch.object(m.time,'sleep'):
            self.assertEqual(m.registry_json_request(m.DC_LICENSE_API,deadline),{})
            self.assertEqual([c.kwargs['request_timeout'] for c in fetch.call_args_list],[15,20])
            self.assertTrue(all(c.args[1]==deadline for c in fetch.call_args_list))
        with patch.object(m,'identity_fetch',side_effect=TimeoutError('down')) as fetch,patch.object(m.time,'sleep'):
            with self.assertRaises(TimeoutError):m.registry_json_request(m.DC_LICENSE_API,deadline)
            self.assertEqual(fetch.call_count,2)
        with patch.object(m,'identity_fetch',side_effect=[TimeoutError('first'),'{}']) as fetch:
            m.registry_json_request(m.RI_PUBLIC_SEARCH_API,deadline)
            self.assertEqual([c.kwargs['request_timeout'] for c in fetch.call_args_list],[15,15])

    def test_dc_large_healthy_result_keeps_complete_pagination_in_one_budget(self):
        from datetime import date
        stamp=int(time.time()*1000)
        rows=[{'attributes':{'OBJECTID':i+1,'CUSTOMERNUMBER':str(68000000+i),
            'ENTITYNAME':'Example Foundation '+str(i),'LICENSESTATUS':'Active',
            'BUSINESSACTIVITY':'Charitable Solicitation','DATAREFRESHEDON':stamp,
            'LICENSEENDDATE':'2027-12-31','PREMISEINDC':'Yes'}} for i in range(519)]
        stop=time.monotonic()+35.5
        with patch.object(m,'registry_json_request',side_effect=[
            {'features':rows[:500],'exceededTransferLimit':True},
            {'features':rows[500:],'exceededTransferLimit':False}]) as request:
            records,freshness=m.dc_charity_records(self.org,stop,['%EXAMPLE%'])
        self.assertEqual(len(records),519)
        self.assertEqual([c.kwargs['payload']['resultOffset'] for c in request.call_args_list],[0,500])
        self.assertTrue(all(c.args[1]==stop for c in request.call_args_list))
        self.assertIn(date.today().isoformat(),freshness)

if __name__=='__main__':unittest.main()
