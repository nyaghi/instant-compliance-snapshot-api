"""Same bounded queries; only completed broader zero responses cover subsets."""
import ast,os,subprocess,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import registry_snapshot_server as m
from testing.capacity_lab.test_mi_name_transport import URL,RESULT,FORM,body

class QueryOrder(unittest.TestCase):
    def setUp(self):
        self.org=SimpleNamespace(organization_name='Example Relief, Inc.',ein='123456789')
        token=m.LAB_LOOKUP_MODE_CONTEXT.set('sales');self.addCleanup(m.LAB_LOOKUP_MODE_CONTEXT.reset,token)
        for p in [patch.object(m,'APP_VERSION','test-performance-lab'),patch.dict(os.environ,{'PUBLIC_BASE_URL':'https://instant-compliance-snapshot-api-hn4v.onrender.com','CE_LAB_MI_QUERY_DOMINANCE':'1'})]:
            p.start();self.addCleanup(p.stop)

    def response(self,source,url):
        r=MagicMock();r.status_code=200;r.url=url;r.history=[];r.iter_content.return_value=[source.encode()];return r

    def test_same_four_queries_and_independent_aliases_retained(self):
        names=['Example Relief, Inc.','Example Relief','The Example Relief','Community Alliance']
        with patch.object(m,'organization_name_variants',return_value=names):
            with patch.dict(os.environ,{'CE_LAB_MI_QUERY_DOMINANCE':'0'}):old=m.mi_name_fallback_queries(self.org)
            new=m.mi_name_fallback_queries(self.org)
        self.assertEqual(len(old),4);self.assertCountEqual(old,new)
        self.assertLess(new.index('Example Relief'),new.index('Example Relief, Inc.'))
        self.assertIn('Community Alliance',new)

    def test_unrelated_query_order_unchanged_and_no_fifth_query_added(self):
        names=['Example Relief, Inc.','Community Alliance','Family Care','Animal Rescue','Fifth Name']
        with patch.object(m,'organization_name_variants',return_value=names):
            with patch.dict(os.environ,{'CE_LAB_MI_QUERY_DOMINANCE':'0'}):old=m.mi_name_fallback_queries(self.org)
            self.assertEqual(old,m.mi_name_fallback_queries(self.org));self.assertEqual(len(old),4)

    def test_only_narrower_terminal_punctuation_is_covered(self):
        for a,b in [('Example Relief','Example Relief, Inc.'),('Example Relief','The Example Relief. Foundation'),('EXAMPLE RELIEF','example relief;')]:
            self.assertTrue(m.mi_completed_query_covers(a,b))
        for a,b in [('Example Relief,','Example Relief'),('Example Relief Inc.','Example Relief Inc'),('Example Relief','Example Reliefer'),("People's Relief",'Peoples Relief'),('ABC Relief','A.B.C. Relief'),('Example Relief','Example Cancer Fund'),('','Example Relief')]:
            self.assertFalse(m.mi_completed_query_covers(a,b))

    def test_complete_broader_zero_can_skip_narrower_but_not_distinct_alias(self):
        s=MagicMock();s.request.side_effect=[self.response(FORM,URL),self.response(body('Example Relief'),RESULT),self.response(FORM,URL),self.response(body('Community Alliance'),RESULT)]
        with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief','Example Relief, Inc.','Community Alliance']):
            self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+30),['Example Relief','Community Alliance'])
        self.assertEqual(s.request.call_count,4)

    def test_positive_partial_or_wrong_echo_never_covers_narrower_queries(self):
        for source in [body('Example Relief','1'),body('Example Relief')[:-7],body('Other Relief')]:
            s=MagicMock();s.request.side_effect=[self.response(FORM,URL),self.response(source,RESULT)]
            with patch.object(m,'mi_name_fallback_queries',return_value=['Example Relief','Example Relief, Inc.']):
                self.assertEqual(m.mi_name_http_empty_queries(s,self.org,{},time.perf_counter()+30),[])

    def test_standard_nonlab_disabled_and_other_origin_keep_prior_order_and_coverage(self):
        for mode,version,env in [('standard','test-performance-lab',{}),('sales','staging',{}),('sales','test-performance-lab',{'CE_LAB_MI_QUERY_DOMINANCE':'0'}),('sales','test-performance-lab',{'PUBLIC_BASE_URL':'https://staging.compliance-express.com'})]:
            token=m.LAB_LOOKUP_MODE_CONTEXT.set(mode)
            try:
                with patch.object(m,'APP_VERSION',version),patch.dict(os.environ,env),patch.object(m,'organization_name_variants',return_value=['Example Relief, Inc.','Example Relief']):
                    self.assertFalse(m.lab_mi_query_dominance_enabled())
                    self.assertEqual(m.mi_name_fallback_queries(self.org)[0],'Example Relief, Inc.')
                    self.assertFalse(m.mi_completed_query_covers('Example Relief','Example Relief, Inc.'))
            finally:m.LAB_LOOKUP_MODE_CONTEXT.reset(token)

    def test_trial_activation_changes_only_the_existing_sales_gate(self):
        root=Path(m.__file__).parent
        old=ast.parse(subprocess.check_output(['git','show','42e6756:registry_snapshot_server.py'],cwd=root).decode())
        new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'))
        names={'lab_mi_query_dominance_enabled','mi_name_fallback_queries','mi_completed_query_covers','mi_name_http_empty_queries'}
        before={n.name:n for n in old.body if isinstance(n,ast.FunctionDef) and n.name in names}
        after={n.name:n for n in new.body if isinstance(n,ast.FunctionDef) and n.name in names}
        self.assertEqual(set(before),names);self.assertEqual(set(after),names)
        for name in names-{'lab_mi_query_dominance_enabled'}:
            self.assertEqual(ast.dump(before[name]),ast.dump(after[name]),name)
        gate=after['lab_mi_query_dominance_enabled']
        self.assertEqual(ast.unparse(gate.body[0].value.values[-1]),"LAB_LOOKUP_MODE_CONTEXT.get() == 'sales'")
        self.assertEqual(ast.unparse(gate.body[0].value.values[0]),"APP_VERSION.endswith('-performance-lab')")
        self.assertEqual(ast.unparse(gate.body[0].value.values[1]),'performance_origin_enabled()')

if __name__=='__main__':unittest.main()
