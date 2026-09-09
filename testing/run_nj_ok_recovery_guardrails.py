"""Delayed NJ evidence and OK query-order controls; offline, no registry calls."""
import ast,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class Tests(unittest.TestCase):
    def org(self,name='Example Relief',ein='123456789'):
        return c.checker.Organization(name,ein)

    def test_existing_frame_does_not_require_another_click(self):
        frame=SimpleNamespace(url='https://example.test/CHR-Public-Details-Page/',content=lambda:'Example Relief 123456789 Next Filing Due: 12/31/2026')
        page=SimpleNamespace(frames=[frame])
        with patch.object(c,'registry_page_body',return_value='Compliant'):
            self.assertIn('12/31/2026',c.nj_detail_body(page,self.org()))

    def test_stalled_selected_frame_is_reloaded_once(self):
        page=Mock(url='https://charportal.dca.njoag.gov/Charity-Registration/CHR-Public-Search-Page/')
        locator=page.locator.return_value.first
        locator.get_attribute.return_value='/CHR-Public-Details-Page/?id=record-id&rid=filing-id'
        frame=locator.element_handle.return_value.content_frame.return_value
        with patch.object(c,'nj_loaded_detail_body',return_value='confirmed fiscal evidence') as read:
            self.assertEqual(c.nj_reload_detail_body(page,self.org()),'confirmed fiscal evidence')
        frame.goto.assert_called_once_with('https://charportal.dca.njoag.gov/CHR-Public-Details-Page/?id=record-id&rid=filing-id',wait_until='domcontentloaded',timeout=15000)
        read.assert_called_once_with(page,self.org(),wait_seconds=8.0)

    def test_reload_rejects_untrusted_or_incomplete_record_url(self):
        for source in ['https://example.test/CHR-Public-Details-Page/?id=x&rid=y','/CHR-Public-Details-Page/?id=x','/CHR-Public-Search-Page/']:
            page=Mock(url='https://charportal.dca.njoag.gov/')
            page.locator.return_value.first.get_attribute.return_value=source
            self.assertEqual(c.nj_reload_detail_body(page,self.org()),'')
            page.locator.return_value.first.element_handle.assert_not_called()

    def test_master_reloads_only_missing_current_and_applies_recovered_date(self):
        tree=ast.parse(Path(c.__file__).read_text())
        fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_state_lookup')
        branch=next(x for x in ast.walk(fn) if isinstance(x,ast.If) and ast.unparse(x.test)=="state == 'NJ'")
        result=c.checker.StateResult('Example Relief','123456789','NJ','Current','')
        result.status_reason='NJ_RAW_COMPLIANT_STATUS_NO_FILING_PERIOD_EVIDENCE'
        recover=Mock(return_value='Next Filing Due: 12/31/2026')
        ns=dict(c.__dict__);ns.update(page=None,org=self.org(),search_nj_with_name_fallback=lambda p,o:result,nj_detail_body=lambda p,o:'Compliant',nj_reload_detail_body=recover)
        exec(compile(ast.fix_missing_locations(ast.Module(body=branch.body,type_ignores=[])),'NJ master recovery','exec'),ns)
        self.assertEqual(c.public_status(result),'Upcoming Filing');recover.assert_called_once()
        self.assertTrue(any('bounded reload' in x for x in result.source_attempts))

    def test_attached_empty_field_waits_for_value(self):
        clock=[0.0];frame=Mock(url='https://example.test/CHR-Public-Details-Page/')
        frame.content.side_effect=['Example Relief <input id="crsm_fiscalyearenddate" value="">','Example Relief <input id="crsm_fiscalyearenddate" value="2025-06-30">']
        with patch.object(c.time,'monotonic',side_effect=lambda:clock[0]),patch.object(c.time,'sleep',side_effect=lambda n:clock.__setitem__(0,clock[0]+n)):
            body=c.nj_loaded_detail_body(SimpleNamespace(frames=[frame]),self.org(),1)
        self.assertIn('2025-06-30',body);self.assertEqual(frame.content.call_count,2)

    def test_other_record_date_is_not_accepted(self):
        frame=SimpleNamespace(url='https://example.test/CHR-Public-Details-Page/',content=lambda:'Unrelated Charity 999999999 Next Filing Due: 12/31/2026')
        self.assertEqual(c.nj_loaded_detail_body(SimpleNamespace(frames=[frame]),self.org()),'')

    def test_late_date_recovers_only_incomplete_current(self):
        tree=ast.parse(Path(c.__file__).read_text())
        fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run_state_lookup')
        branch=next(x for x in ast.walk(fn) if isinstance(x,ast.If) and ast.unparse(x.test)=="state == 'NJ'")
        for status,reason,expected in [('Current','NJ_RAW_COMPLIANT_STATUS_NO_FILING_PERIOD_EVIDENCE','Upcoming Filing'),('Current','','Current'),('Exempt','','Exempt'),('Closed / Withdrawn / Canceled','','Closed / Withdrawn / Canceled'),('Delinquent','','Delinquent')]:
            with self.subTest(status=status,reason=reason):
                result=c.checker.StateResult('Example Relief','123456789','NJ',status,'')
                result.raw_status_text='Compliant | NJ filing-period evidence not visible'
                result.status_reason=reason
                ns=dict(c.__dict__);ns.update(page=None,org=self.org(),public_status=lambda r:r.status,search_nj_with_name_fallback=lambda p,o:result,nj_detail_body=lambda p,o:'Next Filing Due: 12/31/2026')
                exec(compile(ast.fix_missing_locations(ast.Module(body=branch.body,type_ignores=[])),'NJ master branch','exec'),ns)
                self.assertEqual(result.status,expected)

    def planned(self,name,match_query=None):
        queries=[]
        def search(page,org,module):
            queries.append(org.organization_name)
            return SimpleNamespace(organization_name=org.organization_name,status='Current' if org.organization_name==match_query else 'Not Registered',matched_registry_name=name if org.organization_name==match_query else '',raw_status_text='No safely matching filing number link',source_note='',success=True)
        with patch.object(c,'search_ok_precise',side_effect=search),patch.object(c,'public_status',side_effect=lambda r:r.status):
            result=c.search_ok_with_variants(None,self.org(name),SimpleNamespace())
        return queries,result

    def test_specific_phrase_precedes_broad_words(self):
        queries,result=self.planned('National Marrow Donor Program','National Marrow Donor')
        self.assertEqual(queries,['National Marrow Donor']);self.assertEqual(result.status,'Current')

    def test_general_phrase_order_and_negative_controls(self):
        for name in ['Example Children Relief Foundation','Regional Animal Rescue Society','Community Housing Assistance Program']:
            with self.subTest(name=name):
                queries,result=self.planned(name)
                self.assertGreaterEqual(len(queries[0].split()),2)
                self.assertEqual(len(queries),len(set(q.casefold() for q in queries)))
                self.assertLessEqual(len(queries),c.OK_QUERY_LIMIT)
                self.assertEqual(result.status,'Not Registered')

    def test_broad_fallback_still_can_find_exact_identity(self):
        queries,_=self.planned('Example Children Relief Foundation')
        probe=next(q for q in queries if len(q.split())==1)
        actual,result=self.planned('Example Children Relief Foundation',probe)
        self.assertIn(probe,actual);self.assertEqual(result.status,'Current')

if __name__=='__main__':unittest.main()
