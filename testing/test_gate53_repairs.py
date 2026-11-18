"""70 distinct recorded inputs per state; offline parser and DOM contracts.

Source-backed defect fixtures are separate from generated edge-case variants.
These tests do not claim 140 independent live registry adjudications.
"""
import ast, html, json, socket, subprocess, time, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import MagicMock, Mock, patch
import registry_snapshot_server as c
from deployment import pa_detail_evidence as pa

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'testing/fixtures/gate53'
ROSTER=json.loads((P/'LOCAL-70.json').read_text())
BASE='e1543fa83fcb03703d80a16f7667326eec52cc27'
RESULTS=[]
def prior(path,name,space):
    source=subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    namespace=dict(space);exec(compile(ast.Module(body=[node],type_ignores=[]),'RI-'+path,'exec'),namespace)
    return namespace[name]

def ga_body(name, identifier='EXEMPT',kind='Exempt Charity',raw='Active',expiry='',profession='Charities'):
    values=dict(full_name=name,license_no=identifier,license_type=kind,status=raw,expiry=expiry,profession=profession)
    return ''.join('<span id="_ctl0__ctl1_'+k+'">'+html.escape(v)+'</span>' for k,v in values.items())

def outcome(fn,*args):
    try:return dict(result=fn(*args),error=None)
    except ValueError as e:return dict(result=None,error=str(e))

class Gate53(unittest.TestCase):
    def setUp(self):
        self.network=patch.object(socket.socket,'connect',side_effect=AssertionError('Offline suite forbids network'))
        self.network.start()
    def tearDown(self):self.network.stop()

    def test_GA_actual_detail(self):
        body=(P/'GA-HILLSDALE.html').read_text(encoding='utf-8')
        before=prior('registry_snapshot_server.py','ga_charity_detail_html',vars(c))
        self.assertIn('EXEMPT marker',outcome(before,body,'EXEMPT','Hillsdale College')['error'])
        actual=c.ga_charity_detail_html(body,'EXEMPT','Hillsdale College')
        self.assertEqual((actual['status'],actual['raw_status'],actual['license_category']),('Exempt','Active','Exempt Charity'))

    def test_GA_70_paired_exemption_and_adverse_controls(self):
        before=prior('registry_snapshot_server.py','ga_charity_detail_html',vars(c))
        self.assertEqual(len({x['ein'] for x in ROSTER}),70)
        for i,case in enumerate(ROSTER):
            n=case['name']; body=ga_body(n)
            old=outcome(before,body,'EXEMPT',n);new=outcome(c.ga_charity_detail_html,body,'EXEMPT',n)
            self.assertIsNotNone(old['error']);self.assertEqual(new['result']['status'],'Exempt')
            controls=0
            for identifier,kind,raw,expiry in [
                ('EXEMPT','Exempt Charity','Exempt',''),
                ('CH'+str(10000+i),'Exempt Charity','Active',''),
                ('CH'+str(10000+i),'Exempt Charity','Exempt',''),
                ('CH'+str(10000+i),'Charity','Active','12/31/2030'),
                ('CH'+str(10000+i),'Charity','Active',''),
                ('CH'+str(10000+i),'Charity','Expired','01/01/2020'),
                ('CH'+str(10000+i),'Exempt Charity','Revoked',''),
                ('CH'+str(10000+i),'Exempt Charity','Canceled',''),
                ('EXEMPT','Exempt Charity','Expired','01/01/2020'),
                ('EXEMPT','Charity','Active',''),
                ('EXEMPT','Private Foundations','Active',''),
                ('EXEMPT','agency1prof0licType52004','Active',''),
                ('','Exempt Charity','Active','')]:
                b=ga_body(n,identifier,kind,raw,expiry)
                self.assertEqual(outcome(before,b,identifier,n),outcome(c.ga_charity_detail_html,b,identifier,n),(case,kind,raw))
                controls+=1
            self.assertIsNotNone(outcome(c.ga_charity_detail_html,ga_body(n,expiry='bad date'),'EXEMPT',n)['error'])
            for identifier,kind in [('EXEMPT','Exempt Charity'),('CH'+str(10000+i),'Exempt Charity')]:
                for raw in ['Active','Exempt']:
                    result=c.ga_charity_detail_html(ga_body(n,identifier,kind,raw),identifier,n)
                    self.assertEqual(result['status'],'Exempt')
            for bad_identifier in ['CH999999999','']:
                self.assertIsNotNone(outcome(c.ga_charity_detail_html,body,bad_identifier,n)['error'])
            a=c.ga_charity_record_key(dict(identifier='EXEMPT',name=n,location='Boston MA'))
            b=c.ga_charity_record_key(dict(identifier='EXEMPT',name=n+' Unrelated Foundation',location='Other VA'))
            self.assertNotEqual(a,b)
            RESULTS.append(dict(state='GA',**case,scenario='EXEMPT/Exempt Charity/Active',before='rejected',after='Exempt',unchanged_controls=controls,passed=True))

    def pa_case(self,case,*,old=False,missing_ein=False,numbered=False,fault=''):
        ein=case['ein'];name=case['name'];pid='3603117'
        cells=[name,'','', '12345' if numbered else '', '12/31/2030' if numbered else '', '' if missing_ein else ein,'',case.get('street','330 W Camelback Rd Bldg 26'),'Phoenix','AZ','85017','']
        fields=dict(EntityName=name,RegNum=cells[3],Expdt=cells[4],FederalID=cells[5],account_SecondaryAddressLine1=cells[7],account_SecondaryCity='Phoenix, AZ, 85017')
        if case.get('detail_street'):fields['account_SecondaryAddressLine1']=case['detail_street']
        if fault=='foreign-EIN':fields['FederalID']='999999999'
        if fault=='blank-detail-EIN':fields['FederalID']=''
        if fault=='foreign-name':fields['EntityName']='Another Organization'
        if fault=='foreign-office':fields['account_SecondaryAddressLine1']='Other Street'
        if fault=='partial-registration':cells[3]='12345'
        page=MagicMock();page.url=pa.SEARCH
        rows=[dict(index=0,cells=cells)]
        if fault=='duplicate-row':rows.append(dict(index=1,cells=cells[:]))
        page.locator.return_value.evaluate_all.return_value=rows
        binding='' if fault=='missing-grid-ID' else pid
        page.locator.return_value.nth.return_value.locator.return_value.evaluate.return_value=binding
        page.screenshot.return_value=b'original-grid'
        if fault=='busy-grid':page.wait_for_function.side_effect=TimeoutError('busy')
        popup=Mock();popup.url=pa.DETAIL;popup.screenshot.return_value=b'original-detail'
        reads=0
        def evaluate(script):
            nonlocal reads
            if script==pa.PROBE:
                reads+=1
                return dict(fields,EntityName='Changed after capture') if fault=='mutated-detail' and reads>1 else dict(fields)
            if script==pa.DETAIL_ID:return ['888'] if fault=='stale-ID' else [] if fault=='missing-detail-ID' else [pid]
            return fault!='busy-after'
        popup.evaluate.side_effect=evaluate
        page.expect_popup.return_value.value=popup
        page.expect_popup.return_value.__enter__.return_value=page.expect_popup.return_value
        result=NS(state='PA',success=True,status='Current' if numbered else 'Delinquent',matched_registry_name=name,matched_registry_identifier='12345' if numbered else pid)
        run=NS(state='PA',ein=ein,documents=[],visual_adapter_facts=[])
        if missing_ein:
            run.pa_selected_record=dict(PersonId=int(pid),EntityName=name,EIN=None,CertificateNumber=None,ExpDate=None,AddressLine=cells[7],City=cells[8],StateName=cells[9],Zip=cells[10])
        run.document=lambda *a,**kw:run.documents.append(a)
        token=pa.CURRENT.set(run);deadline=pa.DEADLINE.set(time.monotonic()-.1 if fault=='deadline' else time.monotonic()+20)
        try:
            fn=prior('deployment/pa_detail_evidence.py','capture',vars(pa)) if old else pa.capture
            fn(page,NS(ein=ein),result)
            paired=next((d for d in run.documents if d[2]=='image_pages'),None)
            if paired:
                data=dict(vars(result),ein=ein)
                self.assertTrue(pa.image_bound(run,data,*paired[:3]))
                self.assertFalse(pa.image_bound(run,{**data,'ein':'999999999'},*paired[:3]))
                self.assertFalse(pa.image_bound(run,data,paired[0],paired[1]+b'stale',paired[2]))
            return bool(paired),page.expect_popup.call_count,run.visual_adapter_facts
        finally:pa.CURRENT.reset(token);pa.DEADLINE.reset(deadline)

    def test_PA_70_paired_exact_EIN_blank_details_and_guards(self):
        for case in ROSTER:
            old=self.pa_case(case,old=True);new=self.pa_case(case)
            self.assertEqual(old[:2],(False,0));self.assertEqual(new[:2],(True,1))
            for missing,numbered in [(True,False),(False,True)]:
                self.assertEqual(self.pa_case(case,old=True,missing_ein=missing,numbered=numbered)[:2],self.pa_case(case,missing_ein=missing,numbered=numbered)[:2])
                self.assertTrue(self.pa_case(case,missing_ein=missing,numbered=numbered)[0])
            faults=['foreign-EIN','blank-detail-EIN','foreign-name','foreign-office','partial-registration','duplicate-row','missing-grid-ID','busy-grid','stale-ID','missing-detail-ID','mutated-detail','busy-after','deadline']
            for fault in faults:self.assertFalse(self.pa_case(case,fault=fault)[0],(case,fault))
            RESULTS.append(dict(state='PA',**case,scenario='unique exact EIN, blank certificate/date',before='no detail click',after='bound original pair',unchanged_controls=2,rejected_faults=len(faults),passed=True))

    def test_PA_actual_source_tuple(self):
        row=json.loads((P/'PA-INDEPENDENT-SEARCH.json').read_text())['Table'][0]
        detail=json.loads((P/'PA-INDEPENDENT-DETAIL.json').read_text())
        self.assertEqual((row['PersonId'],detail['Table'][0]['PersonId']),(3603117,3603117))
        self.assertIsNone(row['CertificateNumber']);self.assertIsNone(row['ExpDate'])
        case=dict(name=row['EntityName'],ein=pa.digits(row['EIN']),street=row['AddressLine'],detail_street=detail['Table2'][0]['AddressLine1'])
        self.assertEqual(self.pa_case(case,old=True)[:2],(False,0))
        self.assertEqual(self.pa_case(case)[:2],(True,1))

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gate53)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (P/'LOCAL-RESULTS.json').write_text(json.dumps(dict(baseline=BASE,kind='offline paired parser/mocked DOM contracts; not live source checks',cases=RESULTS,passed=result.wasSuccessful()),indent=2,default=str),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
