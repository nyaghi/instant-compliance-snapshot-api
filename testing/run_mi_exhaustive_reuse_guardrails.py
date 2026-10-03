"""Complete Michigan search reuse preserves every legal/DBA identity boundary."""
import ast
import subprocess
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import registry_snapshot_server as cc
from testing.capacity_lab.test_mi_name_transport import FORM, URL, RESULT

def grid(names, aliases=None):
    aliases=aliases or {}
    rows=[]
    for i,name in enumerate(names,3):
        prefix=f'ctl00_MainContent_GridView1_ctl{i:02d}'
        other=''.join(f'<tr><td>1</td><td class="name">{a}</td><td>Former</td></tr>' for a in [name,*aliases.get(i,[])])
        rows.append(f'''<tr class="RowStyle"><td><span id="{prefix}_lblFileNo">{1000+i}</span></td>
          <td><a id="{prefix}_btnOrgName" href="javascript:__doPostBack('ctl00$MainContent$GridView1$ctl{i:02d}$btnOrgName','')">{name}</a>
          <table id="{prefix}_gvNames"><tr><th>&nbsp;</th><th>Name</th><th>Type</th></tr>{other}</table></td><td>12/31/2027</td></tr>''')
    return '<table id="ctl00_MainContent_GridView1"><tr class="HeaderStyle"><th>AG File#</th><th>Legal Name / Address</th><th>License / Registration<br>Expiration</th></tr>'+''.join(rows)+'</table>'

def source(names,aliases=None):
    return '<html>Results for the following input: Organization Type: Charity or Public Safety Organization Name Includes: Legal Services (All words); '+str(len(names))+' record(s) found '+grid(names,aliases)+'</html>'

class Reuse(unittest.TestCase):
    def setUp(self):
        self.org=SimpleNamespace(organization_name='Legal Services Corporation',ein='521039060')
        self.names=['Legal Services of Eastern Michigan','Michigan Indian Legal Services, Inc.']

    def test_complete_unrelated_grid_is_reusable_without_changing_matching(self):
        self.assertTrue(cc.mi_http_complete_unmatched_grid(source(self.names),self.org,2))

    def test_entire_other_master_and_mi_classification_remain_unchanged(self):
        from testing.capacity_lab.parsing_scope import strip_mi_exhaustive_reuse
        root=Path(cc.__file__).parent
        before=ast.parse(subprocess.check_output(['git','show','0ceb32c194d70f59b15ce1d820b67443d3f50540:registry_snapshot_server.py'],cwd=root).decode('utf-8'))
        after=ast.parse(Path(cc.__file__).read_text(encoding='utf-8'));strip_mi_exhaustive_reuse(after)
        self.assertEqual(ast.dump(before),ast.dump(after))

    def test_mi_probe_and_browser_classification_change_only_the_acquisition_handoff(self):
        root=Path(cc.__file__).parent
        trees=[ast.parse(subprocess.check_output(['git','show','0ceb32c194d70f59b15ce1d820b67443d3f50540:registry_snapshot_server.py'],cwd=root).decode('utf-8')),ast.parse(Path(cc.__file__).read_text(encoding='utf-8'))]
        funcs=[{n.name:n for n in t.body if isinstance(n,ast.FunctionDef)} for t in trees]
        fn=funcs[1]['search_mi_name_fallback']
        assignments=[n for n in fn.body if isinstance(n,ast.Assign) and ast.unparse(n.targets[0])=='completed_unmatched_queries']
        self.assertEqual(len(assignments),1)
        self.assertEqual(ast.unparse(assignments[0].value),"set(progress.get('http_completed_unmatched_name_queries', [])) if trial_identity() else set()")
        fn.body.remove(assignments[0])
        loop=next(n for n in fn.body if isinstance(n,ast.For) and ast.unparse(n.target)=='variant')
        block=loop.body.pop(0)
        self.assertEqual(ast.unparse(block.test),'variant in completed_unmatched_queries')
        self.assertIsInstance(block.body[-1],ast.Continue)
        self.assertEqual(len(block.body),2)
        self.assertEqual(ast.unparse(block.body[0].value.func),'result.source_attempts.append')
        self.assertEqual(ast.dump(funcs[0]['search_mi_name_fallback']),ast.dump(fn))
        fn=funcs[1]['search_mi_http_completion_probe'];hits=0
        for node in ast.walk(fn):
            if not hasattr(node,'body') or not isinstance(node.body,list):continue
            node.body[:]=[n for n in node.body if not (isinstance(n,ast.If) and ast.unparse(n.test)=='trial_identity() and mi_http_completed_ein_empty(submitted, formatted_ein)')]
        for node in ast.walk(fn):
            if not hasattr(node,'body') or not isinstance(node.body,list):continue
            for i,n in enumerate(node.body):
                if isinstance(n,ast.If) and ast.unparse(n.test)=='trial_identity()':
                    self.assertEqual([ast.unparse(v.targets[0]) for v in n.body],['unmatched','result._cc_mi_completed_empty_names','result._cc_mi_completed_unmatched_names'])
                    self.assertEqual(ast.unparse(n.body[1].value), 'mi_name_http_empty_queries(session, org, headers, lookup_deadline, unmatched_queries=unmatched)')
                    self.assertEqual(ast.unparse(n.body[2].value),'unmatched')
                    self.assertEqual(len(n.orelse),1);node.body[i:i+1]=n.orelse;hits+=1
        self.assertEqual(hits,1);self.assertEqual(ast.dump(funcs[0]['search_mi_http_completion_probe']),ast.dump(fn))

    def test_legal_name_or_former_dba_candidate_keeps_original_detail_path(self):
        self.assertFalse(cc.mi_http_complete_unmatched_grid(source([self.org.organization_name]),self.org,1))
        self.assertFalse(cc.mi_http_complete_unmatched_grid(source(self.names,{3:[self.org.organization_name]}),self.org,2))

    def test_actual_master_browser_confirmation_preserves_evidence_but_controls_fallback(self):
        tree=ast.parse(Path(cc.__file__).read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if getattr(n,'name','')=='run_state_lookup')
        branch=next(n for n in ast.walk(fn) if isinstance(n,ast.If) and ast.unparse(n.test)=="state == 'MI'")
        code=compile(ast.fix_missing_locations(ast.Module(body=branch.body[:8],type_ignores=[])),str(cc.__file__),'exec')
        for status in ['Not Registered','Current','Unable to Verify']:
            probe=SimpleNamespace(success=True,status='Not Registered',reason_code='NO_CANDIDATES_AFTER_COMPLETED_SEARCH',
                _cc_mi_completed_empty_names=['First Query'],_cc_mi_completed_unmatched_names=['Legal Services'])
            browser=SimpleNamespace(status=status,raw_status_text='',source_note='',error='')
            page=SimpleNamespace();confirm=MagicMock(return_value=browser);fallback=MagicMock(return_value=browser)
            values={**cc.__dict__,'org':self.org,'page':page,'lookup_started':time.perf_counter(),
                'mi_progress':{},'trial_identity':lambda:True,'public_status':lambda r:r.status,
                'search_mi_http_completion_probe':lambda *a,**k:probe,
                'search_bundled_extension_state':confirm,'search_mi_name_fallback':fallback,'MI_ENABLE_NAME_FALLBACK':True}
            exec(code,values)
            confirm.assert_called_once_with(page,self.org,'MI')
            self.assertIs(values['mi_probe_result'],probe)
            if status=='Not Registered':
                fallback.assert_called_once_with(page,self.org)
                self.assertEqual(page._cc_mi_search_progress['http_completed_empty_name_queries'],['First Query'])
                self.assertEqual(page._cc_mi_search_progress['http_completed_unmatched_name_queries'],['Legal Services'])
            else:
                fallback.assert_not_called()

    def test_complete_ein_empty_proof_reuses_only_same_input_and_keeps_name_fallback(self):
        tree=ast.parse(Path(cc.__file__).read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if getattr(n,'name','')=='run_state_lookup')
        branch=next(n for n in ast.walk(fn) if isinstance(n,ast.If) and ast.unparse(n.test)=="state == 'MI'")
        code=compile(ast.fix_missing_locations(ast.Module(body=branch.body[:8],type_ignores=[])),str(cc.__file__),'exec')
        for identity in [(self.org.organization_name,'521039060'),('Other','521039060'),(self.org.organization_name,'999999999')]:
            probe=SimpleNamespace(success=True,status='Not Registered',reason_code='NO_CANDIDATES_AFTER_COMPLETED_SEARCH',
                raw_status_text='No results found',source_note='',error='',_cc_mi_completed_exact_ein_empty=identity,
                _cc_mi_completed_empty_names=['Legal Services Corporation'],_cc_mi_completed_unmatched_names=['Legal Services'])
            confirm=MagicMock(return_value=probe);fallback=MagicMock(return_value=probe);page=SimpleNamespace()
            values={**cc.__dict__,'org':self.org,'page':page,'lookup_started':time.perf_counter(),'mi_progress':{},
                'trial_identity':lambda:True,'public_status':lambda r:r.status,'search_mi_http_completion_probe':lambda *a,**k:probe,
                'search_bundled_extension_state':confirm,'search_mi_name_fallback':fallback,'MI_ENABLE_NAME_FALLBACK':True}
            exec(code,values)
            if identity==(self.org.organization_name,'521039060'): confirm.assert_not_called()
            else: confirm.assert_called_once_with(page,self.org,'MI')
            fallback.assert_called_once_with(page,self.org)
            self.assertEqual(page._cc_mi_search_progress['http_completed_unmatched_name_queries'],['Legal Services'])

    def test_exact_ein_empty_response_proof_fails_closed_for_incomplete_and_ambiguous_sources(self):
        source=('<html><body><h1>Search Results</h1><span id="ctl00_MainContent_lblSearchResults">'
                'Results for the following input: Organization Type: Charity or Public Safety Organization<br>'
                'EIN: 52-1039060; 0 record(s) found</span><table id="ctl00_MainContent_GridView1">'
                '<tr><td colspan="3">No records found for your search criteria</td></tr></table></body></html>')
        def response(text=source,url='https://www.ag.state.mi.us/CharitableTrust/frmSearchResults.aspx',status=200,history=None):
            return SimpleNamespace(text=text,url=url,status_code=status,history=history or [])
        self.assertTrue(cc.mi_http_completed_ein_empty(response(),'52-1039060'))
        for bad in [source[:-7],source.replace('52-1039060','52-9999999'),source.replace('EIN:', 'Name Includes: Other; EIN:'),
                    source.replace('0 record(s)','1 record(s)'),source.replace('Charity or Public Safety Organization','Charity Professional Fundraiser'),
                    source.replace('No records found for your search criteria','Loading'),source.replace('</td>','<a href="x">Candidate</a></td>'),
                    source.replace('</body>','CAPTCHA</body>'),source.replace('<h1>','<h2>').replace('</h1>','</h2>'),
                    source.replace('</table>',''),source.replace('</body>','<table id="ctl00_MainContent_GridView1"></table></body>')]:
            with self.subTest(source=bad):self.assertFalse(cc.mi_http_completed_ein_empty(response(bad),'52-1039060'))
        for url in ['http://www.ag.state.mi.us/CharitableTrust/frmSearchResults.aspx','https://other.test/CharitableTrust/frmSearchResults.aspx',
                    'https://www.ag.state.mi.us/CharitableTrust/frmDefault.aspx','https://www.ag.state.mi.us/CharitableTrust/frmSearchResults.aspx?name=other']:
            self.assertFalse(cc.mi_http_completed_ein_empty(response(url=url),'52-1039060'))
        self.assertFalse(cc.mi_http_completed_ein_empty(response(status=503),'52-1039060'))
        self.assertFalse(cc.mi_http_completed_ein_empty(response(history=[response(url='https://other.test/')]),'52-1039060'))

    def test_partial_count_pagination_headers_anchor_and_aliases_fail_closed(self):
        s=source(self.names)
        for bad,count in [(s,3),(s,101),(s.replace('Legal Name / Address','Name'),2),
                (s.replace('</table>','',1),2),(s.replace('_btnOrgName','_OtherButton',1),2),
                (s.replace('1004','1003'),2),(s.replace('<table id=', '<script>x</script><table id=').replace('</td><td>12/', '<script>x</script></td><td>12/'),2),
                (s.replace('ctl00$MainContent$GridView1$ctl03$btnOrgName', 'Other$ctl03$btnOrgName'),2),
                (s.replace('class="name"','class="unknown"',1),2),(s.replace('<th>Name</th>','<th>Changed</th>'),2)]:
            with self.subTest(count=count,bad=bad):self.assertFalse(cc.mi_http_complete_unmatched_grid(bad,self.org,count))

    def response(self,s,url):
        r=MagicMock();r.status_code=200;r.url=url;r.history=[];r.iter_content.return_value=[s.encode()];return r

    def run_source(self,s,trial=True):
        session=MagicMock();session.request.side_effect=[self.response(FORM,URL),self.response(s,RESULT)];unmatched=[]
        with patch.object(cc,'trial_identity',return_value={'origin':'trial'} if trial else None),patch.object(cc,'mi_name_fallback_queries',return_value=['Legal Services']):
            zero=cc.mi_name_http_empty_queries(session,self.org,{},time.perf_counter()+30,unmatched_queries=unmatched)
        return zero,unmatched,session

    def test_unmatched_is_separate_from_zero_and_uses_same_complete_query(self):
        zero,unmatched,session=self.run_source(source(self.names))
        self.assertEqual(zero,[]);self.assertEqual(unmatched,['Legal Services']);self.assertEqual(session.request.call_count,2)
        self.assertTrue(all(c.kwargs['verify'] for c in session.request.call_args_list))

    def test_nontrial_positive_unmatched_and_wrong_echo_never_reuse(self):
        self.assertEqual(self.run_source(source(self.names),trial=False)[:2],([],[]))
        for s in [source(self.names).replace('Legal Services (All words)','Other (All words)'),source(self.names).replace('</html>',' CAPTCHA</html>'),source(self.names)[:-7],source(self.names).replace('2 record(s)','1 record(s)')]:
            self.assertEqual(self.run_source(s)[:2],([],[]))

    def test_positive_legal_or_alias_never_becomes_completed_unmatched(self):
        for s in [source([self.org.organization_name]),source(self.names,{3:[self.org.organization_name]})]:
            self.assertEqual(self.run_source(s)[:2],([],[]))

    def test_only_exact_completed_query_skips_browser_not_another_reviewed_alias(self):
        page=MagicMock();page._cc_mi_lookup_deadline=time.perf_counter()+30
        page._cc_mi_search_progress={'identity':(self.org.organization_name,'521039060'),'http_completed_unmatched_name_queries':['Legal Services']}
        with patch.object(cc,'trial_identity',return_value={'origin':'trial'}),patch.object(cc,'mi_name_fallback_queries',return_value=['Legal Services']):
            result=cc.search_mi_name_fallback(page,self.org)
        self.assertTrue(result.success);self.assertEqual(result.status,cc.checker.STATUS_NOT_REGISTERED)
        self.assertTrue(any('every legal and alias' in text for text in result.source_attempts))
        page.goto.assert_not_called()
        with patch.object(cc,'trial_identity',return_value={'origin':'trial'}),patch.object(cc,'mi_name_fallback_queries',return_value=['Other Reviewed Alias']),patch.object(cc.state_extension_module('MI'),'open_search_form',return_value=False):
            result=cc.search_mi_name_fallback(page,self.org)
        self.assertFalse(result.success)

if __name__=='__main__':unittest.main(verbosity=2)
