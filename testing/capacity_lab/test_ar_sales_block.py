"""Explicit blocked responses release Sales capacity without inventing status."""
import ast,os,subprocess,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import registry_snapshot_server as m

class AccessBlock(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_AR_BLOCK_RETRY':'terminal'})
        self.version=patch.object(m,'APP_VERSION','fixture-performance-lab');self.env.start();self.version.start()
        self.addCleanup(self.env.stop);self.addCleanup(self.version.stop)
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)
    def blocked(self):return SimpleNamespace(state='AR',status='Site Not Reachable',success=False,error='AR registry returned bot-verification or block page after submit',raw_status_text='access blocked',source_note='State access could not be confirmed.')
    def test_sales_returns_first_explicit_block_without_sleep_or_cookie_reset(self):
        result=self.blocked();page=Mock()
        with patch.object(m,'AR_LAST_LOOKUP_FINISHED',0),patch.object(m,'search_ar_name_variants_once',return_value=result) as lookup,patch.object(m.time,'sleep') as sleep:
            self.assertIs(m.search_ar_serialized(page,SimpleNamespace()),result)
        lookup.assert_called_once();sleep.assert_not_called();page.context.clear_cookies.assert_not_called()
    def test_standard_preserves_existing_recovery(self):
        m.LAB_LOOKUP_MODE_CONTEXT.set('standard');result=self.blocked();good=SimpleNamespace(state='AR',status='Current',success=True,error='')
        with patch.object(m,'AR_LAST_LOOKUP_FINISHED',0),patch.object(m,'search_ar_name_variants_once',side_effect=[result,good]) as lookup,patch.object(m.time,'sleep') as sleep:
            self.assertIs(m.search_ar_serialized(Mock(),SimpleNamespace()),good)
        self.assertEqual(lookup.call_count,2);sleep.assert_called_once_with(m.AR_TRANSIENT_RETRY_DELAY_SECONDS)
    def test_outer_semantic_layer_does_not_retry_explicit_block(self):
        result=vars(self.blocked())
        with patch.object(m,'run_state_lookup',return_value=result) as lookup,patch.object(m.time,'sleep') as sleep:
            actual=m.run_single_state_lookup_reliably('Control','123456789','AR')
        lookup.assert_called_once();sleep.assert_not_called();self.assertEqual(actual['status'],'Site Not Reachable');self.assertFalse(actual['success'])
    def test_only_known_explicit_block_can_end_recovery(self):
        for change in [dict(state='FL'),dict(success=True),dict(status='Not Registered'),dict(error='AR transport timed out'),dict(error='unparsed response')]:
            d=vars(self.blocked());d.update(change);self.assertFalse(m.lab_sales_ar_access_block_is_terminal(d))
        for version,origin,flag in [('production','https://instant-compliance-snapshot-api-hn4v.onrender.com','terminal'),('x-performance-lab','https://staging.compliance-express.com','terminal'),('x-performance-lab','https://instant-compliance-snapshot-api-hn4v.onrender.com','')]:
            with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,{'PUBLIC_BASE_URL':origin,'CE_LAB_AR_BLOCK_RETRY':flag}):self.assertFalse(m.lab_sales_ar_access_block_is_terminal(self.blocked()))
    def test_sales_transport_timeout_can_recover(self):
        failed={'state':'AR','status':'Site Not Reachable','success':False,'error':'AR transport timed out'}
        good={'state':'AR','status':'Current','success':True,'error':''}
        with patch.object(m,'run_state_lookup',side_effect=[failed,good]) as lookup,patch.object(m.time,'sleep'):
            self.assertIs(m.run_single_state_lookup_reliably('Control','123456789','AR'),good)
        self.assertEqual(lookup.call_count,2)
    def test_other_master_logic_and_budgets_are_byte_equivalent_ast(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','f56a83d:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse((root/'registry_snapshot_server.py').read_text(encoding='utf-8'))
        def normalize(tree):
            tree.body=[n for n in tree.body if getattr(n,'name','')!='lab_sales_ar_access_block_is_terminal' and not (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='LAB_LOOKUP_MODE_CONTEXT' for t in n.targets))]
            for node in tree.body:
                if getattr(node,'name','')=='search_ar_serialized':
                    for child in ast.walk(node):
                        if isinstance(child,ast.If) and isinstance(child.test,ast.BoolOp) and isinstance(child.test.values[0],ast.Call) and getattr(child.test.values[0].func,'id','')=='lab_sales_ar_access_block_is_terminal':child.test=child.test.values[1]
                if getattr(node,'name','')=='run_single_state_lookup_reliably':
                    loop=next(n for n in node.body if isinstance(n,ast.For))
                    loop.body=[n for n in loop.body if not (isinstance(n,ast.If) and any(isinstance(x,ast.Call) and getattr(x.func,'id','')=='lab_sales_ar_access_block_is_terminal' for x in ast.walk(n.test)))]
            return ast.dump(tree)
        self.assertEqual(normalize(old),normalize(new))

if __name__=='__main__':unittest.main()
