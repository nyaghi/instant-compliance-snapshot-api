"""Authoritative detail/EIN binding, conservative fallback and exact scope."""
import ast,copy,json,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import registry_snapshot_server as m

class PublicDetail(unittest.TestCase):
    def setUp(self):
        self.org=m.checker.Organization('Example Relief','123456789');self.module=m.load_wa_nm_module()
        self.row={'FEINNumber':'123456789','EntityName':'EXAMPLE RELIEF','BusinessType':'Charity','CFTId':17,'RegistrationNumber':'1100017','TotalPageCount':0,'Criteria':{'TotalRowCount':0}}
        self.detail={**self.row,'CharityID':17,'BusinessType':'CHARITABLE ORGANIZATION','Status':'Active','RenewalDate':'2030-11-30T00:00:00','IsOptionalRegistration':False}
        self.token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,self.token)
        for p in [patch.object(m,'APP_VERSION','test-performance-lab'),patch.dict(os.environ,{'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_WA_READY_STEPS':'1','CE_LAB_WA_PUBLIC_DETAIL':'1'})]:
            p.start();self.addCleanup(p.stop)

    def read(self,rows=None,detail=None):
        with patch.object(m,'identity_fetch',side_effect=[json.dumps([self.row] if rows is None else rows).encode(),json.dumps(self.detail if detail is None else detail).encode()]) as fetch:
            result=m.lab_wa_public_detail(self.org,self.module)
        return result,fetch

    def test_unique_current_detail_uses_same_interpreter_and_fresh_requests(self):
        result,fetch=self.read();self.assertEqual(result.status,'Current');self.assertEqual(result.verified_registry_ein,'123456789')
        self.assertEqual(fetch.call_count,2)
        a,b=fetch.call_args_list
        self.assertIn('FEINNo=123456789',a.kwargs['data'].decode());self.assertIn('CharityID=17&Type=Charity',b.args[0])
        self.assertEqual(a.args[1],b.args[1]);self.assertEqual(a.kwargs['request_timeout'],9);self.assertEqual(b.kwargs['request_timeout'],6)
        result2,fetch2=self.read();self.assertEqual(fetch2.call_count,2);self.assertEqual(result2.status,result.status)

    def test_empty_multiple_truncated_wrong_ein_or_wrong_type_keeps_browser(self):
        for rows in [[],[self.row,self.row],{},[None],[{**self.row,'FEINNumber':'987654321'}],[{**self.row,'BusinessType':'Trust'}],[{**self.row,'CFTId':True}],[{**self.row,'TotalPageCount':2}],[{**self.row,'Criteria':{'TotalRowCount':2}}],[{**self.row,'RegistrationNumber':''}]]:
            with self.subTest(rows=rows):
                result,fetch=self.read(rows);self.assertIsNone(result);self.assertEqual(fetch.call_count,1)

    def test_detail_must_bind_same_id_registration_ein_and_charity_type(self):
        for key,value in [('FEINNumber','987654321'),('CFTId',18),('CharityID',18),('RegistrationNumber','1100018'),('BusinessType','COMMERCIAL FUNDRAISER'),('Status',''),('IsOptionalRegistration',None),('RenewalDate','0001-01-01T00:00:00'),('RenewalDate','not a date')]:
            with self.subTest(key=key):self.assertIsNone(self.read(detail={**self.detail,key:value})[0])

    def test_existing_delinquent_exempt_and_closed_rules_are_retained(self):
        for updates,expected in [({'RenewalDate':'2020-11-30T00:00:00'},'Delinquent'),({'IsOptionalRegistration':True,'RenewalDate':None},'Exempt'),({'Status':'Closed','RenewalDate':None},self.module.STATUS_CLOSED)]:
            with self.subTest(updates=updates):self.assertEqual(self.read(detail={**self.detail,**updates})[0].status,expected)

    def test_search_status_cannot_override_authoritative_detail(self):
        self.row.update(Status='Active',RenewalDate='2030-11-30T00:00:00')
        self.detail.update(Status='Closed',RenewalDate=None)
        self.assertEqual(self.read()[0].status,self.module.STATUS_CLOSED)

    def test_display_retains_registry_aka_without_changing_identity(self):
        self.row['AKANames']=' EXAMPLE FORMER NAME'
        result,fetch=self.read()
        self.assertEqual(result.matched_registry_name,'EXAMPLE RELIEF( EXAMPLE FORMER NAME)')
        self.assertEqual(result.verified_registry_ein,'123456789')

    def test_timeout_block_and_invalid_payload_fall_back_never_negative(self):
        for reply in [TimeoutError('test'),ValueError('test'),b'<html>Human verification</html>',b'null']:
            with patch.object(m,'identity_fetch',side_effect=reply if isinstance(reply,Exception) else None,return_value=reply if not isinstance(reply,Exception) else None):
                self.assertIsNone(m.lab_wa_public_detail(self.org,self.module))

    def test_standard_nonlab_or_disabled_never_calls_source(self):
        for mode,version,env in [('standard','x-performance-lab',{}),('sales','staging',{}),('sales','x-performance-lab',{'PUBLIC_BASE_URL':'https://staging.compliance-express.com'}),('sales','x-performance-lab',{'CE_LAB_WA_PUBLIC_DETAIL':'0'}),('sales','x-performance-lab',{'CE_LAB_WA_READY_STEPS':'0'})]:
            token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
            try:
                with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,env),patch.object(m,'identity_fetch') as fetch:
                    self.assertIsNone(m.lab_wa_public_detail(self.org,self.module));fetch.assert_not_called()
            finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_no_other_master_behavior_changed(self):
        from testing.capacity_lab.wa_public_scope import strip_wa_public
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','c8534e4:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));strip_wa_public(new)
        self.assertEqual(ast.dump(old),ast.dump(new))

if __name__=='__main__':unittest.main()
