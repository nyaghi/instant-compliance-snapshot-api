"""Offline regression tests. Never launches a browser or contacts a registry."""
import ast
import copy
import json
import re
import socket
import subprocess
import time
import unittest
from contextlib import contextmanager, ExitStack
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, MagicMock, patch

import registry_snapshot_server as c
from deployment import alias_ownership as own, pa_detail_evidence as pa, pa_selected_evidence as grid
from deployment.state_snapshots import matching_reference

BASE = '6379513c521b92af53d15396e69c92323f35619b'
ROOT = Path(__file__).resolve().parents[1]
ROSTER = json.loads((ROOT/'testing/fixtures/fresh-five/LOCAL-70.json').read_text(encoding='utf-8'))
OLD = ast.parse(subprocess.check_output(['git','show',BASE+':registry_snapshot_server.py'],cwd=ROOT))
ROWS = []


@contextmanager
def baseline(*names):
    saved = {name:getattr(c,name) for name in names}
    nodes = [node for node in OLD.body if isinstance(node,ast.FunctionDef) and node.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'recorded-RC-baseline','exec'),vars(c))
    try: yield
    finally:
        for name,fn in saved.items(): setattr(c,name,fn)


def save(state, case, scenario, before, after, passed):
    ROWS.append(dict(state=state,organization=case['name'],ein=case['ein'],scenario=scenario,
                     baseline=before,candidate=after,passed=bool(passed)))
    assert passed, ROWS[-1]


@contextmanager
def offline():
    # A missed mock fails loudly instead of quietly performing a live check.
    with patch.object(socket.socket,'connect',side_effect=AssertionError('Network forbidden in local validation')):
        yield


@contextmanager
def names_for(case, aliases=()):
    token=c.REVIEWED_NAME_CONTEXT.set({case['ein']:tuple(aliases)})
    with patch.object(c,'known_names_for_ein',side_effect=lambda ein: list(aliases) if c.canonical_ein_digits(ein)==case['ein'] else []):
        try: yield
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)


class Gate51Local(unittest.TestCase):
    def setUp(self): self.guard=offline();self.guard.__enter__()
    def tearDown(self): self.guard.__exit__(None,None,None)

    def test_70_discovery_ownership_cases_and_recorded_klove(self):
        for i,case in enumerate(ROSTER):
            alias='Distinctive Outreach '+str(i)
            source=dict(organization_records=[dict(ein=case['ein'],address_role='organization',
                street='2000 Reams Fleming Blvd',state='TN',postal_code='37064')])
            proof=dict(name=alias,fein='990434313',principaladdress='2000 Reams Fleming Blvd',
                       principalstate='TN',principalzipcode='37064',source_url='https://official.example/record')
            item=dict(name=alias,verified=True,evidence=[dict(type='DBA')])
            for owner in [case['ein'],'990434313']:
                row={**proof,'fein':owner}
                with patch.object(own,'records',return_value=[row]):
                    after=own.review_discovery(c,[copy.deepcopy(item)],[source],case['name'],case['ein'],time.monotonic()+3)[0]
                expected=owner!=case['ein']
                save('discovery',case,'same-EIN' if not expected else 'separate-owner',True,
                     bool(after.get('identity_conflict')),bool(after.get('identity_conflict'))==expected)
                self.assertEqual(after['verified'],not expected)
        # Public recorded name/office/EIN, independent of the generated controls.
        case=dict(name='Educational Media Foundation',ein='942816342')
        row=dict(name='K-LOVE, INC.',fein='99-0434313',principaladdress='2000 Reams Fleming Blvd',
                 principalstate='TN',principalzipcode='37064',source_url='https://data.colorado.gov/resource/37wu-kn3g.json')
        office=own.office(c,row['principaladdress'],'TN','37064')
        for name in ['KLOVE INC','K-LOVE, Inc.','K LOVE']:
            with patch.object(c,'identity_fetch',return_value=json.dumps([row]).encode()):
                own.RECORD_CACHE.pop(('alias-legal-owner',re.sub('[^A-Z0-9]','',c.normalized_match_name(name).upper())),None)
                self.assertEqual(own.conflict(c,name,case['ein'],[office],time.monotonic()+3)['ein'],'990434313')

    def test_ownership_no_guess_no_repeated_successful_query(self):
        org=c.checker.Organization('Educational Media Foundation','942816342')
        row=dict(name='K-LOVE, INC.',fein='990434313',principaladdress='2000 Reams Fleming Blvd',
                 principalstate='TN',principalzipcode='37064')
        office=own.office(c,row['principaladdress'],'TN','37064')
        key=('alias-legal-owner',re.sub('[^A-Z0-9]','',c.normalized_match_name(row['name']).upper()))
        own.RECORD_CACHE.clear()
        with patch.object(c,'identity_fetch',return_value=json.dumps([row]).encode()) as fetch:
            for _ in range(8):self.assertEqual(own.conflict(c,row['name'],org.ein,[office],time.monotonic()+3)['decision'],'different_ein')
            self.assertEqual(fetch.call_count,1)
        for rows in [[],[row,{**row,'fein':org.ein}],[{**row,'fein':''}],
                     [{**row,'principaladdress':'100 Different Road'}]]:
            with patch.object(own,'records',return_value=rows):self.assertFalse(own.conflict(c,row['name'],org.ein,[office],time.monotonic()+3))
        with patch.object(c,'identity_fetch',side_effect=TimeoutError):
            own.RECORD_CACHE.clear()
            self.assertFalse(own.conflict(c,row['name'],org.ein,[office],time.monotonic()+3))
        with patch.object(c,'identity_fetch') as fetch:
            self.assertEqual(own.records(c,'K-LOVE',time.monotonic()-1),[]);fetch.assert_not_called()

    def test_70_each_licensed_state_primary_names_and_alias_conflicts(self):
        for state in ['AL','DC','TN','NC','NV','RI','GA','IL']:
            for i,case in enumerate(ROSTER):
                org=c.checker.Organization(case['name'],case['ein'])
                def run(row, before=False):
                    with ExitStack() as stack:
                        if before:stack.enter_context(baseline('licensed_charity_identity'))
                        for fn in ['reconciled_registry_address','licensed_charity_street_evidence']:
                            stack.enter_context(patch.object(c,fn,return_value={'decision':'corroborated'}))
                        stack.enter_context(patch.object(c,'licensed_charity_foreign_ein',return_value={}))
                        stack.enter_context(patch.object(c,'il_missing_fein_identity',return_value={'decision':'corroborated'}))
                        return c.licensed_charity_identity(org,copy.deepcopy(row),state,time.monotonic()+3)
                with names_for(case):
                    row=dict(name=case['name'],ein=case['ein'],location='Franklin, TN 37064')
                    with patch.object(c,'identity_fetch') as fetch:
                        before=run(row,True);after=run(row)
                        save(state,case,'exact-EIN-primary',before,after,before==after=='accepted')
                        fetch.assert_not_called()
                alias='Distinctive Outreach '+str(i)
                with names_for(case,[alias]),patch.object(own,'candidate_conflict',return_value={'decision':'different_ein','ein':'990434313'}):
                    row=dict(name=alias,ein='',location='Franklin, TN 37064')
                    before=run(row,True);after=run(row)
                    save(state,case,'related-alias-different-EIN',before,after,after=='rejected')
                    with patch.object(own,'candidate_conflict',return_value={}):
                        unchanged=run(row)
                    save(state,case,'no-different-owner-proof',before,unchanged,before==unchanged)

    def test_70_complete_discovery_requests(self):
        for i,case in enumerate(ROSTER):
            alias='Distinctive Outreach '+str(i)
            base=dict(complete=True,names=[],organization_records=[])
            legal=c.identity_candidate(case['name'],'CO','Registered name','https://source.example/legal')
            other=c.identity_candidate(alias,'NM','Other Name','https://source.example/alias')
            owner=dict(name=alias,fein='990434313',principaladdress='2000 Reams Fleming Blvd',
                       principalstate='TN',principalzipcode='37064',source_url='https://source.example/owner')
            def cached(source,ein):
                data={**base,'source':source}
                if source=='CO':data.update(names=[legal],organization_records=[dict(ein=case['ein'],
                    street='2000 Reams Fleming Blvd',state='TN',postal_code='37064',address_role='organization')])
                if source=='NM':data['names']=[other]
                return copy.deepcopy(data)
            def run(before=False):
                with ExitStack() as stack:
                    if before:stack.enter_context(baseline('discover_organization_names'))
                    stack.enter_context(patch.object(c,'identity_cached_source_result',side_effect=cached))
                    stack.enter_context(patch.object(own,'records',return_value=[owner]))
                    result=c.discover_organization_names(case['name'],case['ein'])
                selected=next(item for item in result['names'] if item['name']==alias)
                return bool(selected.get('identity_conflict'))
            before,after=run(True),run()
            save('discovery',case,'full-discovery-route',before,after,not before and after)

    def test_70_connecticut_rows(self):
        for i,case in enumerate(ROSTER):
            org=c.checker.Organization(case['name'],case['ein'])
            for is_alias in [False,True]:
                label='Distinctive Outreach '+str(i) if is_alias else case['name']
                html='<b class="headline6">'+label+'</b><b>Credential</b><p>CHR.0000001</p><b>Status</b><p>ACTIVE</p>'
                def run(before=False):
                    with ExitStack() as stack:
                        if before:stack.enter_context(baseline('ct_direct_result_from_row'))
                        stack.enter_context(patch.object(c,'ct_direct_detail_text',return_value=''))
                        stack.enter_context(patch.object(own,'candidate_conflict',return_value={'decision':'different_ein'} if is_alias else {}))
                        result,_=c.ct_direct_result_from_row(org,html,[case['name'],label],'https://www.elicense.ct.gov/')
                        return result.status if result else 'excluded'
                with names_for(case,[label] if is_alias else []):
                    before,after=run(True),run()
                    save('CT',case,'different-owner' if is_alias else 'primary-row',before,after,
                         after=='excluded' if is_alias else before==after=='Current')

    def test_70_new_hampshire_dataset_rows(self):
        for i,case in enumerate(ROSTER):
            org=c.checker.Organization(case['name'],case['ein'])
            for is_alias in [False,True]:
                label='Distinctive Outreach '+str(i) if is_alias else case['name']
                record=dict(registry_name=label,registry_id=str(10000+i),status_code='G',due_date=date(2027,12,31),due_raw='12/31/2027')
                def run(before=False):
                    with ExitStack() as stack:
                        if before:stack.enter_context(baseline('search_nh_live_pdf'))
                        stack.enter_context(patch.object(c,'nh_live_pdf_records',return_value=([record],'11/17/2026')))
                        stack.enter_context(patch.object(own,'candidate_conflict',return_value={'decision':'different_ein'} if is_alias else {}))
                        return c.search_nh_live_pdf(org).status
                with names_for(case,[label] if is_alias else []):
                    before,after=run(True),run()
                    save('NH',case,'different-owner' if is_alias else 'primary-row',before,after,
                         after.casefold()=='not registered' if is_alias else before==after)

    def test_70_mississippi_connector_replays(self):
        for i,case in enumerate(ROSTER):
            org=c.checker.Organization(case['name'],case['ein'])
            for described in [False,True]:
                label=case['name']+(', A Georgia nonprofit corporation' if described else '')
                def run(before=False,proof=True):
                    calls=[]
                    def evidence(query):
                        calls.append(query)
                        if query['operation']=='search':
                            return dict(state='MS',query=query,complete=True,verification_pending=False,total=1,
                                rows=[dict(name=label,identifier='100016765',raw_status='Current - Exempted')])
                        fields={'Name':label,'Filing Number':'100016765','Filing Status':'Current - Exempted',
                                'Expiration Date':'','Registered Name':label}
                        if not before:fields['Public Text']='Registered Name: '+label+'\nAddress\n2000 Reams Fleming Blvd\nFranklin, TN 37064\nContact Information'
                        return dict(query=query,complete=True,source_url=c.MS_BROWSER_SOURCE,fields=fields)
                    with ExitStack() as stack:
                        if before:stack.enter_context(baseline('ms_browser_lookup','ms_browser_clean_evidence'))
                        stack.enter_context(patch.object(c,'ms_name_search_plan',return_value=[case['name'],'An Independent Outreach Name']))
                        stack.enter_context(patch.object(c,'ms_legal_description_identity',return_value={'address':{'decision':'corroborated'}} if proof else {}))
                        result=c.ms_browser_lookup(org,evidence)
                    return {'status':result.status,'success':result.success,'requests':len(calls),'review':bool(getattr(result,'_cc_identity_review',None))}
                with names_for(case):
                    before,after=run(True),run()
                    save('MS',case,'corporate-description' if described else 'complete-name',before,after,
                         (after['status']=='Exempt' and after['success'] and after['requests']==2) if described else before==after)
                    if described:
                        review=run(False,False)
                        self.assertTrue(review['review']);self.assertFalse(review['success']);self.assertEqual(review['requests'],2)

    def test_70_each_tn_nm_bound_source_names(self):
        for state in ['TN','NM']:
            for i,case in enumerate(ROSTER):
                name=case['name']+' d/b/a Community Learning'
                identifier='CO'+str(4000+i) if state=='TN' else c.format_ein(case['ein'])
                url='https://source.example/detail/'+identifier
                org=c.checker.Organization(case['name'],case['ein'])
                def run(before=False):
                    result=c.checker.StateResult(case['name'],case['ein'],state,'Current',url)
                    result.success=True;result.matched_registry_name=name;result.matched_registry_identifier=identifier
                    result._cc_selected_source_identity=(state,name,identifier,url)
                    with baseline('fill_registry_match_from_text','normalize_registry_match_fields') if before else ExitStack():
                        c.fill_registry_match_from_text(result,'',org)
                        c.normalize_registry_match_fields(result,org)
                    data=dict(state=state,ein=case['ein'],status=result.status,success=True,
                              matched_registry_name=result.matched_registry_name,matched_registry_identifier=identifier)
                    ref=dict(state=state,ein=case['ein'],identifier=identifier,record_name=name,operation='detail')
                    return dict(name=result.matched_registry_name,linked=matching_reference(data,[ref]) is ref,status=result.status)
                with names_for(case):
                    before,after=run(True),run()
                    save(state,case,'full-source-DBA-link',before,after,after['linked'] and after['name']==name and after['status']=='Current')
                    for change in [('state','CT'),('matched_registry_identifier','different'),('source_url',url+'stale')]:
                        result=c.checker.StateResult(case['name'],case['ein'],state,'Current',url)
                        result.success=True;result.matched_registry_name=name;result.matched_registry_identifier=identifier
                        result._cc_selected_source_identity=(state,name,identifier,url)
                        setattr(result,*change)
                        # A changed identifier/URL must no longer invoke the preservation shortcut.
                        with patch.object(c,'clean_registry_name',return_value='sentinel') as cleanup:
                            c.normalize_registry_match_fields(result,org)
                        self.assertTrue(cleanup.called)

    def test_70_pennsylvania_grid_and_blank_detail(self):
        old_source=subprocess.check_output(['git','show',BASE+':deployment/pa_detail_evidence.py'],cwd=ROOT)
        node=next(n for n in ast.parse(old_source).body if isinstance(n,ast.FunctionDef) and n.name=='capture')
        old_space=dict(vars(pa));exec(compile(ast.Module(body=[node],type_ignores=[]),'RC-PA-adapter','exec'),old_space)
        old_capture=old_space['capture']
        for i,case in enumerate(ROSTER):
            record=dict(EntityName=case['name'],PersonId=3604297+i,EIN=None,CertificateNumber=None,
                        ExpDate=None,AddressLine='1 Main Street',City='Boston',StateName='MA',Zip='02115')
            cells=[case['name'],'','','','','','',record['AddressLine'],record['City'],record['StateName'],record['Zip'],'']
            org=NS(ein=case['ein'])
            result=NS(state='PA',success=True,status='Delinquent',matched_registry_name=case['name'],
                      matched_registry_identifier=str(record['PersonId']))
            def setup(fault=''):
                page=MagicMock();page.url=grid.URL
                response=Mock(status=200,url=grid.API);response.request.method='POST'
                response.request.post_data_json=dict(EntityName=case['name'],EIN='',SearchCriteria='Contains',SearchCategory='Charities_IPP')
                response.json.return_value=dict(Table=[record],Table1=[dict(RESULTCOUNT=1)])
                page.expect_response.return_value.__enter__.return_value=NS(value=response)
                page.expect_response.return_value.value=response
                def wait(script,**kwargs):
                    if fault=='busy-grid' and script==pa.SETTLED:raise TimeoutError('overlay remains')
                page.wait_for_function.side_effect=wait
                page.evaluate.side_effect=lambda script,*args: False if script==pa.SETTLED and fault=='busy-after' else True if script==pa.SETTLED else json.dumps(cells)
                locator=page.locator.return_value
                locator.evaluate_all.return_value=[dict(index=0,cells=cells)]
                locator.nth.return_value.locator.return_value.evaluate.return_value=str(record['PersonId'])
                page.screenshot.return_value=b'fixture-original-grid'
                popup=Mock();popup.url=pa.DETAIL
                fields=dict(EntityName=case['name'],RegNum='',Expdt='',FederalID='',account_SecondaryAddressLine1=record['AddressLine'],account_SecondaryCity='Boston, MA, 02115')
                if fault=='different-office':fields['account_SecondaryAddressLine1']='20 Other Street'
                if fault=='different-EIN':fields['FederalID']='990434313'
                if fault=='different-name':fields['EntityName']='A Different Institution'
                def evaluate(script):
                    if script==pa.PROBE:return fields
                    if script==pa.DETAIL_ID:return [str(record['PersonId']+1)] if fault=='stale-ID' else [] if fault=='missing-ID' else [str(record['PersonId'])]
                    return True
                popup.evaluate.side_effect=evaluate;popup.screenshot.return_value=b'fixture-original-detail'
                page.expect_popup.return_value.value=popup
                page.expect_popup.return_value.__enter__.return_value=page.expect_popup.return_value
                run=NS(state='PA',ein=case['ein'],documents=[],visual_adapter_facts=[])
                run.page=lambda p:run.documents.append((grid.URL,b'fixture-original-grid','image','',{}))
                run.document=lambda *a,**k:run.documents.append((*a,k))
                return page,run
            def run_adapter(before=False,fault=''):
                page,run=setup(fault)
                token=pa.CURRENT.set(run);stop=pa.DEADLINE.set(time.monotonic()+20)
                try:
                    grid.capture(page,org,result,[record],case['name'],time.monotonic()+10)
                    if before:old_capture(page,org,result)
                    else:pa.capture(page,org,result)
                    data=dict(vars(result),ein=case['ein'])
                    paired=next((d for d in run.documents if d[2]=='image_pages'),None)
                    linked=bool(paired and grid.image_bound(run,data,*paired[:3]))
                    if paired and not before:
                        self.assertTrue(linked)
                        for field,value in [('ein','990434313'),('matched_registry_name','Other'),('matched_registry_identifier','other'),('state','TN'),('success',False)]:
                            self.assertFalse(grid.image_bound(run,{**data,field:value},*paired[:3]))
                        self.assertFalse(grid.image_bound(run,data,paired[0],paired[1]+b'stale',paired[2]))
                    return dict(grid=any(d[2]=='image' for d in run.documents),
                        detail=any(d[2]=='image_pages' for d in run.documents),
                        linked=linked,
                        waits=len(page.wait_for_function.call_args_list),
                        detail_closed=page.expect_popup.return_value.value.close.call_count)
                finally:pa.CURRENT.reset(token);pa.DEADLINE.reset(stop)
            before,after=run_adapter(True),run_adapter()
            save('PA',case,'blank-PersonId-selected-detail',before,after,
                 before['grid'] and not before['detail'] and after['grid'] and after['detail'] and after['linked'] and after['detail_closed']==1)
            for fault in ['busy-grid','busy-after','stale-ID','missing-ID','different-EIN','different-name','different-office']:
                checked=run_adapter(False,fault)
                self.assertFalse(checked['detail'],(case,fault,checked))
                if fault.startswith('busy'):self.assertFalse(checked['grid'])

    def test_ms_strict_office_and_schema_guards(self):
        name='Emory University, A Georgia nonprofit corporation'
        text='Registered Name: '+name+'\nAddress\n201 Dowman Drive\nAtlanta, GA 30322\nContact Information'
        fields=c.ms_detail_identity_fields(text,name)
        self.assertEqual(fields['region'],'GA');self.assertEqual(fields['postal_code'],'30322')
        org=c.checker.Organization('Emory University','580566256')
        external=NS(matched_registry_name=name,ms_detail_identity=fields)
        def identify(org,row,state,deadline):
            row['address_evidence']={'decision':'corroborated'};return 'accepted'
        with patch.object(c,'licensed_charity_identity',side_effect=identify),names_for(dict(name=org.organization_name,ein=org.ein)):
            for decision in ['different_ein','conflict','unavailable','corroborated']:
                with patch.object(c,'licensed_charity_street_evidence',return_value={'decision':decision}):
                    proof=c.ms_legal_description_identity(org,external,time.perf_counter()+3)
                    self.assertEqual(bool(proof),decision=='corroborated')
        for wrong in ['Emory University Healthcare Foundation, A Georgia nonprofit corporation',
                      'Emory University Georgia Chapter, A Georgia nonprofit corporation']:
            self.assertNotEqual(c.normalized_match_name(c.ms_described_legal_name(wrong)),c.normalized_match_name(org.organization_name))
        query=dict(state='MS',operation='detail',identifier='100016765')
        values={'Name':name,'Filing Number':'100016765','Filing Status':'Current - Exempted','Expiration Date':'','Registered Name':name}
        for extra in [{},{'Public Text':text}]:
            payload=dict(query=query,complete=True,fields={**values,**extra},source_url=c.MS_BROWSER_SOURCE)
            self.assertEqual(c.ms_browser_clean_evidence(payload,query)['fields'],payload['fields'])
        for extra in [{'Public Text':'a'*12001},{'Unexpected':'value'},{'Public Text':{}}]:
            with self.assertRaises(ValueError):c.ms_browser_clean_evidence(dict(query=query,complete=True,fields={**values,**extra},source_url=c.MS_BROWSER_SOURCE),query)

    def test_recorded_sources_reproduce_ownership_and_link_corrections(self):
        owners=json.loads((ROOT/'testing/fixtures/gate51/KLOVE-OWNERS.json').read_text(encoding='utf-8'))['records']
        case=dict(name='Educational Media Foundation',ein='942816342')
        org=c.checker.Organization(case['name'],case['ein'])
        source=dict(organization_records=[dict(ein=case['ein'],address_role='organization',
                    street='2000 Reams Fleming Blvd',state='TN',postal_code='37064')])
        with names_for(case,['K-LOVE']),patch.object(c,'identity_source_result',return_value=source),patch.object(c,'identity_fetch',return_value=json.dumps(owners).encode()):
            for state in ['AL','DC','TN','NC','NV','RI','GA','IL']:
                row=dict(name='KLOVE INC',ein='',street='2000 Reams Fleming Blvd',region='TN',postal_code='37064',location='Franklin, TN')
                with patch.object(c,'reconciled_registry_address',return_value={'decision':'corroborated'}):
                    self.assertEqual(c.licensed_charity_identity(org,row,state,time.monotonic()+3),'rejected')
                self.assertEqual(row['address_evidence']['ein'],'990434313')
        for proof in json.loads((ROOT/'testing/fixtures/gate51/ELDERHOSTEL-BINDING.json').read_text(encoding='utf-8')):
            state=proof['state'];url='https://source.example/detail'
            org=c.checker.Organization('Elderhostel, Inc.','042632526')
            result=c.checker.StateResult(org.organization_name,org.ein,state,'Upcoming Filing',url)
            result.success=True;result.matched_registry_name=proof['source_name'];result.matched_registry_identifier=proof['identifier']
            result._cc_selected_source_identity=(state,proof['source_name'],proof['identifier'],url)
            c.normalize_registry_match_fields(result,org)
            ref=dict(state=state,ein=org.ein,identifier=proof['identifier'].replace('-','') if state=='NM' else proof['identifier'],
                     record_name=proof['source_name'],operation='detail')
            self.assertIs(matching_reference(dict(state=state,ein=org.ein,status='Upcoming Filing',success=True,
                matched_registry_name=result.matched_registry_name,matched_registry_identifier=result.matched_registry_identifier),[ref]),ref)

    def test_ownership_time_is_shared_across_rows_not_restarted(self):
        org=NS();clock=[100.0];used=[]
        def check(master,org,name,deadline,row):
            duration=min(2.0,max(0,deadline-clock[0]));used.append(duration);clock[0]+=duration;return {}
        with patch.object(own.time,'monotonic',side_effect=lambda:clock[0]),patch.object(own,'_candidate_conflict',side_effect=check):
            for _ in range(5):own.candidate_conflict(c,org,'Alias',200,state='NH')
            self.assertEqual(used,[2.0,1.0,0.0,0.0,0.0])
            own.candidate_conflict(c,org,'Alias',200,state='CT')
            self.assertEqual(used[-1],2.0)

    def test_pa_probe_javascript_without_any_browser(self):
        # Node evaluates the exact DOM probes against small object fixtures.
        # This checks the predicates, not the real site's Angular layout.
        script=r'''const assert=require('node:assert');const probes=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
        let row={PersonId:3604297}, parentId=3604297, busy=[];
        const panel={querySelectorAll:()=>[]};
        global.document={querySelector:()=>panel,querySelectorAll:()=>busy};
        global.window={angular:{element:()=>({scope:()=>undefined,controller:()=>({PersonId:parentId,EntityDetails:row})})}};
        global.getComputedStyle=x=>x.style;
        const ids=eval('('+probes.id+')'),settled=eval('('+probes.settled+')');
        assert.deepStrictEqual(ids(),['3604297']);row={};assert.deepStrictEqual(ids(),[]);
        row={PersonId:123};assert.strictEqual(ids().length,2);
        assert.strictEqual(settled(),true);busy=[{getClientRects:()=>[1],style:{visibility:'visible',display:'block'}}];
        assert.strictEqual(settled(),false);busy[0].style.display='none';assert.strictEqual(settled(),true);
        console.log('PA ID and loading predicates passed; no browser launched');'''
        result=subprocess.run(['node','-e',script],input=json.dumps({'id':pa.DETAIL_ID,'settled':pa.SETTLED}),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_ms_multiple_records_do_not_shortcut_the_identity_decision(self):
        org=c.checker.Organization('Emory University','580566256')
        label='Emory University, A Georgia nonprofit corporation'
        def evidence(query):
            if query['operation']=='search':
                rows=[dict(name=label,identifier=str(n),raw_status='Current - Exempted') for n in [100016765,100016766]]
                return dict(state='MS',query=query,complete=True,verification_pending=False,total=2,rows=rows)
            return dict(query=query,complete=True,source_url=c.MS_BROWSER_SOURCE,fields={
                'Name':label,'Filing Number':query['identifier'],'Filing Status':'Current - Exempted',
                'Expiration Date':'','Registered Name':label})
        with names_for(dict(name=org.organization_name,ein=org.ein)),patch.object(c,'ms_name_search_plan',return_value=[org.organization_name]),patch.object(c,'ms_legal_description_identity') as proof:
            result=c.ms_browser_lookup(org,evidence)
        self.assertFalse(result.success);self.assertEqual(len(result._cc_identity_review['records']),2)
        proof.assert_not_called()

    def test_live_capped_ownership_query_is_narrowed_before_interpretation(self):
        from urllib.parse import parse_qs,urlsplit
        owners=json.loads((ROOT/'testing/fixtures/gate51/KLOVE-OWNERS.json').read_text(encoding='utf-8'))['records']
        def fetch(url,deadline,**kwargs):
            where=parse_qs(urlsplit(url).query)['$where'][0]
            self.assertIn("upper(principalstate) = 'TN'",where)
            self.assertIn("principalzipcode like '37064%'",where)
            self.assertEqual(kwargs['request_timeout'],2.0)
            return json.dumps(owners).encode()
        own.RECORD_CACHE.clear()
        office=own.office(c,'2000 Reams Fleming Blvd','TN','37064')
        with patch.object(c,'identity_fetch',side_effect=fetch) as request:
            proof=own.conflict(c,'K-LOVE','942816342',[office],time.monotonic()+3)
        self.assertEqual(proof['ein'],'990434313');self.assertEqual(request.call_count,1)
        with patch.object(c,'identity_fetch',return_value=json.dumps(owners*34).encode()):
            own.RECORD_CACHE.clear()
            self.assertFalse(own.conflict(c,'K-LOVE','942816342',[office],time.monotonic()+3))

    def test_discovery_waits_for_owner_offices_and_merges_duplicate_aliases(self):
        case=dict(name='Educational Media Foundation',ein='942816342')
        alias=c.identity_candidate('K-LOVE','NM','Other Name','https://source.example/alias')
        office=dict(ein=case['ein'],address_role='organization',street='2000 Reams Fleming Blvd',state='TN',postal_code='37064')
        sources=[dict(source='NM',names=[alias],organization_records=[])]
        with patch.object(own,'conflict',return_value={}) as proof:
            self.assertFalse(own.discovery_conflicts(c,sources,case['name'],case['ein'],time.monotonic()+3))
            proof.assert_not_called()
            sources += [dict(source='CO',names=[],organization_records=[office]),dict(source='OH',names=[alias],organization_records=[])]
            own.discovery_conflicts(c,sources,case['name'],case['ein'],time.monotonic()+3)
            self.assertEqual(proof.call_count,1)

    def test_70_each_tn_nm_complete_response_to_original_reference(self):
        for state in ['TN','NM']:
            for i,case in enumerate(ROSTER):
                org=c.checker.Organization(case['name'],case['ein']);name=case['name']+' d/b/a Community Learning'
                identifier='CO'+str(4000+i) if state=='TN' else c.format_ein(case['ein'])
                url='https://source.example/detail/'+identifier
                result=c.checker.StateResult(case['name'],case['ein'],state,'Current',url)
                result.success=True;result.matched_registry_name=name;result.matched_registry_identifier=identifier
                result._cc_selected_source_identity=(state,name,identifier,url)
                with names_for(case),ExitStack() as stack:
                    for fn,value in [('apply_confirmed_feedback_correction',''),('true_status_from_body','Current'),('comments_for_result','Control'),('enrich_registration_date_sources',None),('registration_date_metadata',{}),('renewal_filing_metadata',{})]:
                        stack.enter_context(patch.object(c,fn,return_value=value))
                    data=c.response_data_for_lookup(result,'',org,case['name'],case['ein'],state,time.perf_counter())
                ref=dict(state=state,ein=case['ein'],identifier=identifier,record_name=name,operation='detail')
                self.assertEqual(data['matched_registry_name'],name)
                self.assertIs(matching_reference(data,[ref]),ref)

    def test_pa_real_controller_shape_without_debug_scope(self):
        fixture=json.loads((ROOT/'testing/fixtures/gate51/PA-BLANK-CONTROLLER.json').read_text(encoding='utf-8'))
        script=r'''const assert=require('node:assert'),p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
        const row=p.fixture.grid, detail=p.fixture.detail;
        const values=[row.EntityName,'','',row.CertificateNumber||'','',row.EIN||'','',row.AddressLine,row.City,row.StateName,row.Zip,''];
        const panel={},el={closest:()=>({querySelectorAll:()=>values.map(innerText=>({innerText}))})};
        let rows=[row];
        global.document={querySelector:()=>panel};
        global.window={angular:{element:node=>({scope:()=>undefined,controller:()=>node===panel?detail:{searchResults:rows}})}};
        const ids=eval('('+p.id+')'),grid=eval('('+p.grid+')');
        assert.deepStrictEqual(ids(),['3604297']);assert.strictEqual(grid(el),'3604297');
        detail.EntityDetails.PersonId=123;assert.deepStrictEqual(ids(),['3604297','123']);
        rows=[{...row,EIN:'12-3456789'}];assert.strictEqual(grid(el),'');
        rows=[row,{...row,PersonId:123}];assert.strictEqual(grid(el),'');
        rows=[{...row,AddressLine:'Different office'}];assert.strictEqual(grid(el),'');
        console.log('Recorded Pennsylvania production-controller shape passed');'''
        result=subprocess.run(['node','-e',script],input=json.dumps(dict(fixture=fixture,id=pa.DETAIL_ID,grid=pa.GRID_ID)),text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_70_pa_pair_survives_final_archive_selection_without_printed_id(self):
        import hashlib
        from deployment import state_snapshots as snapshots
        for i,case in enumerate(ROSTER):
            run=snapshots.CaptureRun(case['name'],case['ein'],'PA')
            ident=str(3604297+i);raw=b'actual-pair-contract-'+str(i).encode()
            run.pa_detail_hash=hashlib.sha256(raw).hexdigest()
            run.pa_detail_identity=(case['ein'],case['name'],ident)
            run.documents=[(pa.DETAIL,raw,'image_pages',case['name']+'\nBoston MA',time.time(),'original pair')]
            data=dict(state='PA',ein=case['ein'],status='Delinquent',success=True,
                      matched_registry_name=case['name'],matched_registry_identifier=ident)
            with patch.object(snapshots,'asset_for',side_effect=lambda raw,**kw:dict(kind=kw['kind'])):
                result=run.finish(data)
            self.assertEqual(result['_worker_source_archives'][0]['kind'],'image_pages')
            self.assertNotIn(ident,run.documents[0][3])


if __name__=='__main__':unittest.main(verbosity=2)
