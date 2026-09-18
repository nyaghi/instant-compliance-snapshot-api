"""Reported Sept 17 identity/credential defects, with adversarial controls."""
import io, json, sys, time, unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
F = Path(__file__).parent / 'fixtures' / 'cogency-repair'

class RepairTests(unittest.TestCase):
    def setUp(self):
        c.WI_FINANCIAL_IDENTITY_CACHE.clear()
    def test_location_survives_short_reviewed_alias(self):
        name='Beth Israel Deaconess Hospital – Milton, Inc.'
        token=c.REVIEWED_NAME_CONTEXT.set({'042103604':('Beth Israel Deaconess Hospital',)})
        try:
            targets=c.organization_match_target_variants(name,'042103604')
            for other in ('Beth Israel Deaconess Hospital - Needham, Inc.', 'Beth Israel Deaconess Hospital'):
                self.assertFalse(c.registry_name_is_safe_for_org(other,name,'042103604'))
                self.assertFalse(c.registry_name_is_safe_against_targets(other,targets,name,'042103604'))
            self.assertTrue(c.registry_name_is_safe_for_org('Beth Israel Deaconess Hospital-Milton, Inc.',name,'042103604'))
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_wi_active_primary_identity_wins_both_orders(self):
        old={'registry_name':'USAFA Endowment','primary_registry_name':'Air Force Academy Foundation', 'score':5,
             'identity_preference':0,'detail_status':'License is not current (Expired)','expiration_date':date(2028,1,1)}
        active={**old,'registry_name':'Air Force Academy Foundation','detail_status':'License is current (Active)', 'expiration_date':date(2027,1,1)}
        self.assertTrue(c.wi_better_candidate(active,old));self.assertFalse(c.wi_better_candidate(old,active))
        self.assertFalse(c.wi_better_candidate(dict(active,identity_conflict=True),old))
        self.assertFalse(c.wi_better_candidate(dict(active,score=4),old))

    def test_ct_full_lookup_preserves_original_location_with_reviewed_alias(self):
        name='Beth Israel Deaconess Hospital – Milton, Inc.'
        token=c.REVIEWED_NAME_CONTEXT.set({'042103604':('Beth Israel Deaconess Hospital',)})
        row='<tr><td><b class="headline6">BETH ISRAEL DEACONESS HOSPITAL - NEEDHAM INC</b><b>Credential</b><p>CHR.0059351-EXEMPT</p><b>Status</b><p>ACTIVE</p><b>Credential Description</b><p>PUBLIC CHARITY</p></td></tr>'
        try:
            with patch.object(c,'ct_direct_prepare_session',return_value=(None,{},{})),patch.object(c,'ct_direct_post_query',return_value='Search: '+name+' Showing 1 result(s).'+row),patch.object(c,'ct_direct_detail_text',return_value=''),patch.object(c,'ct_direct_result_from_text') as flatten:
                result=c.search_ct_direct(c.checker.Organization(name,'042103604'))
            flatten.assert_not_called()
            self.assertNotEqual(result.matched_registry_identifier,'CHR.0059351-EXEMPT')
            self.assertEqual(c.public_status(result),'Not Registered')
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_me_same_page_active_credential_has_its_own_fields(self):
        opener=Mock();opener.open.return_value=io.BytesIO((F/'me-CO4010-detail.html').read_bytes())
        row={'name':'Rocky Mountain Elk Foundation','number':'CO4010','href':'detail','status':'Failed to Renew'}
        result=c.me_result_from_search(c.checker.Organization(row['name'],'81-0421425'),row,opener,True,'')
        self.assertEqual(result.matched_registry_identifier,'CO5700')
        self.assertIn('11/30/2026',result.raw_status_text)
        self.assertNotIn('2004',result.raw_status_text)
        self.assertNotIn('Failed to Renew',result.raw_status_text)

    def test_me_empty_widget_never_erases_confirmed_credential(self):
        r=c.checker.StateResult('Example Foundation','123456789','ME','Upcoming Filing','https://example.test',success=True)
        r.matched_registry_name='Example Foundation';r.matched_registry_identifier='CO12345'
        r.raw_status_text='Expiration Date: 11/30/2026'
        c.enrich_me_result_from_body(r,'Disciplinary actions: No records found')
        self.assertEqual(r.status,'Upcoming Filing');self.assertEqual(r.matched_registry_identifier,'CO12345')

    def test_me_empty_widget_does_not_turn_failed_search_negative(self):
        r=c.checker.StateResult('Example Foundation','123456789','ME','Site Not Reachable','https://example.test',success=False)
        c.enrich_me_result_from_body(r,'No records found')
        self.assertEqual(r.status,'Site Not Reachable');self.assertFalse(r.success)

    def test_me_completed_empty_search_still_returns_not_registered(self):
        r=c.checker.StateResult('Example Foundation','123456789','ME','Not Registered','https://example.test',success=True)
        c.enrich_me_result_from_body(r,'0 records found')
        self.assertEqual(r.status,'Not Registered');self.assertTrue(r.success)

    def test_sc_990_header_ein_excludes_paid_preparer(self):
        self.assertEqual(c.form990_pdf_organization_ein((F/'sc-william-alumni-return.pdf').read_bytes(),time.monotonic()+15),'546054289')

    def test_sc_related_entity_requires_document_identity(self):
        self.assertTrue(c.sc_related_entity_requires_ein('College of William & Mary','College of William & Mary Alumni Association'))
        self.assertFalse(c.sc_related_entity_requires_ein('College of William & Mary','College of William & Mary'))
        self.assertFalse(c.sc_related_entity_requires_ein('Example Alumni Association','Example Alumni Association Inc.'))

    def test_nh_one_pass_includes_all_reviewed_names(self):
        org=c.checker.Organization('First Responders Children’s Foundation','05-0536854')
        token=c.REVIEWED_NAME_CONTEXT.set({'050536854':('National Law Enforcement and Firefighters Children’s Foundation',)})
        records=[c.nh_record_from_cells(['42','National Law Enforcement and Firefighters Children’s Foundation','G','11/15/2027'])]
        try:
            with patch.object(c,'nh_live_pdf_records',return_value=(records,'September 11, 2026')) as read:
                result=c.search_snapshot_or_embedded_state(org,'NH')
            read.assert_called_once();self.assertEqual(result.matched_registry_identifier,'42')
            with patch.object(c,'nh_live_pdf_records',return_value=([],'September 11, 2026')) as read:
                result=c.search_snapshot_or_embedded_state(org,'NH')
            read.assert_called_once();self.assertEqual(c.public_status(result),'Not Registered')
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_nh_unreadable_source_remains_unreachable(self):
        with patch.object(c,'nh_live_pdf_records',side_effect=ValueError('incomplete download')):
            result=c.search_snapshot_or_embedded_state(c.checker.Organization('Example Relief','123456789'),'NH')
        self.assertEqual(c.public_status(result),'Site Not Reachable')

    def test_wi_city_similarity_alone_never_confirms_another_city(self):
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'city':'FORT MYERS','state':'FL'}}):
            self.assertTrue(c.wi_minor_city_spelling_difference('650403969','FORT MEYERS, FL'))
            for location in ('NEW YORK, NY','MILWAUKEE, WI','FORT MYERS, WI','FORT LAUDERDALE, FL'):
                self.assertFalse(c.wi_minor_city_spelling_difference('650403969',location))

    def financial(self, changed=False, wrong_ein=False):
        irs=(F/'wi-fgcu-irs990.html').read_bytes()
        if wrong_ein:irs=irs.replace(b'65-0403969',b'12-3456789')
        state=(F/'wi-fgcu-financial-2025.html').read_bytes()
        if changed:state=state.replace(b'25,030,298',b'25,030,299')
        opener=Mock();opener.open.side_effect=[io.BytesIO((F/'wi-fgcu-financial.html').read_bytes()),io.BytesIO(state)]
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'latest_object_id':'202532319349302943'}}), \
             patch.object(c,'identity_fetch',return_value=irs),patch.object(c.urllib.request,'build_opener',return_value=opener):
            return c.wi_financial_identity_evidence('650403969','CredSummaryDetails.aspx?chid=944852&h=847014605','22812-800',0)

    def test_wi_five_same_year_filing_values_corroborate_ein(self):
        self.assertEqual(self.financial().get('decision'),'corroborated')

    def test_wi_one_financial_disagreement_rejects_corroboration(self):
        self.assertEqual(self.financial(changed=True),{})

    def test_wi_wrong_irs_ein_rejects_corroboration(self):
        self.assertEqual(self.financial(wrong_ein=True),{})

    def test_wi_incomplete_financial_page_recovers_selected_credential_session(self):
        opener=Mock()
        opener.open.side_effect=[io.BytesIO(b'<html>Temporarily unavailable</html>'),
            io.BytesIO(b'<html>Temporarily unavailable</html>'),
            io.BytesIO(b'Credential Number: 22812-800'),
            io.BytesIO((F/'wi-fgcu-financial.html').read_bytes()),
            io.BytesIO((F/'wi-fgcu-financial-2025.html').read_bytes())]
        diagnostics={}
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'latest_object_id':'202532319349302943'}}), \
             patch.object(c,'identity_fetch',return_value=(F/'wi-fgcu-irs990.html').read_bytes()), \
             patch.object(c.urllib.request,'build_opener',return_value=opener),patch.object(c.time,'sleep'):
            result=c.wi_financial_identity_evidence('650403969','CredSummaryDetails.aspx?chid=944852&h=847014605','22812-800',0,diagnostics)
        self.assertEqual(result.get('decision'),'corroborated')
        self.assertTrue(diagnostics['credential_session_reload'])

    def test_wi_unavailable_evidence_is_not_cached_as_identity_failure(self):
        self.assertEqual(self.financial(changed=True),{})
        self.assertEqual(self.financial().get('decision'),'corroborated')
        with patch.object(c,'identity_fetch',side_effect=TimeoutError('temporary source failure')):
            self.assertEqual(c.wi_financial_identity_evidence('650403969','CredSummaryDetails.aspx?chid=944852&h=847014605','22812-800',0).get('decision'),'corroborated')

    def test_ny_same_ein_and_address_selects_primary_without_recency_guess(self):
        org=c.checker.Organization('American Friends of Sheba Medical Center, Inc.','237076117')
        primary={'orgID':'49-35-56','ein':org.ein,'orgName':org.organization_name,'address':'6505 Wilshire Blvd','city':'Los Angeles','state':'CA','zip':'90048'}
        other={**primary,'orgID':'05-64-26','orgName':'American Friends of Sheba Medical Center Tel Hashomer'}
        details={row['orgID']:row for row in (primary,other)}
        for rows in ([primary,other],[other,primary]):
            with patch.object(c,'registry_address_evidence') as extra:
                self.assertEqual(c.ny_select_confirmed_duplicate(org,rows,details.__getitem__)['orgID'],primary['orgID'])
                extra.assert_not_called()

    def test_ny_wrong_detail_ein_is_never_name_matched(self):
        org=c.checker.Organization('Example Relief','123456789')
        rows=[{'orgID':str(i),'ein':org.ein,'orgName':org.organization_name} for i in (1,2)]
        with self.assertRaises(ValueError):
            c.ny_select_confirmed_duplicate(org,rows,lambda key:dict(rows[0],ein='987654321'))

    def test_ny_old_blank_date_preserves_newer_confirmed_period(self):
        detail=json.loads((F/'ny-convention-detail.json').read_text())['data']
        dates,ignored=c.ny_confirmed_annual_dates(detail['documents']['Annual Filing for Charitable Organizations'])
        self.assertEqual(max(dates),date(2024,12,31));self.assertEqual(ignored,1)
        session=Mock();session.__enter__=Mock(return_value=session);session.__exit__=Mock(return_value=False)
        def response(data):
            value=Mock();value.json.return_value={'success':True,'statusCode':200,'data':data};return value
        row={key:detail[key] for key in ('orgID','orgName','ein')}
        session.get.side_effect=[response([row]),response(detail)]
        with patch.object(c.curl_requests,'Session',return_value=session):
            result=c.search_ny_direct(c.checker.Organization(detail['orgName'],detail['ein']))
        self.assertTrue(result.success);self.assertEqual(result.computed_due_date,'11/15/2026')
        self.assertEqual(result.matched_registry_identifier,'472245708')
        c.apply_ny_latest_fye_next_cycle_status(c.checker.Organization(detail['orgName'],detail['ein']),result)
        comment=c.comments_for_result_base(result,'',c.public_status(result))
        self.assertIn('older filing',comment);self.assertIn('latest confirmed dated filing',comment)
        self.assertEqual(session.get.call_args_list[0].kwargs['params'],{'ein':'472245708'})

    def test_ny_undated_recent_or_unordered_receipt_still_fails(self):
        dated={'fiscalYearEnd':'12/31/2024','received':'03/17/2026'}
        for unknown in ({'received':'01/01/2025'},{'received':''},{'received':'invalid'},{}):
            with self.subTest(unknown=unknown),self.assertRaises(ValueError):
                c.ny_confirmed_annual_dates([dated,unknown])

    def test_ny_only_undated_history_cannot_establish_latest_period(self):
        with self.assertRaises(ValueError):c.ny_confirmed_annual_dates([{'received':'11/10/2021'}])
        self.assertEqual(c.ny_confirmed_annual_dates([]),([],0))

    def test_ny_invalid_nonempty_date_or_entry_remains_incomplete(self):
        for invalid in ({'fiscalYearEnd':'not a date','received':'11/10/2021'},None):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                c.ny_confirmed_annual_dates([{'fiscalYearEnd':'12/31/2024'},invalid])

    def test_ny_active_is_preferred_only_with_confirmed_same_ein(self):
        org=c.checker.Organization('Example Relief','123456789')
        rows=[{'orgID':str(i),'ein':org.ein,'orgName':org.organization_name,'status':status} for i,status in [(1,'Closed'),(2,'Active')]]
        details={row['orgID']:row for row in rows}
        self.assertEqual(c.ny_select_confirmed_duplicate(org,rows,details.__getitem__)['orgID'],'2')
        rows[0]['status']='Active'
        with self.assertRaises(ValueError):c.ny_select_confirmed_duplicate(org,rows,details.__getitem__)

    def test_ny_conflicting_hq_overrides_identical_name(self):
        org=c.checker.Organization('Example Relief','123456789')
        rows=[{'orgID':str(i),'ein':org.ein,'orgName':org.organization_name,'city':city,'state':'WI'} for i,city in [(1,'Milwaukee'),(2,'Madison')]]
        with patch.object(c,'registry_address_evidence',side_effect=lambda ein,loc:{'decision':'corroborated' if loc.startswith('Madison') else 'conflict'}):
            self.assertEqual(c.ny_select_confirmed_duplicate(org,rows,{r['orgID']:r for r in rows}.__getitem__)['orgID'],'2')

    def test_wv_original_query_precedes_long_former_names(self):
        token=c.REVIEWED_NAME_CONTEXT.set({'810421425':('ROCKY MOUNTAIN ELK FOUNDATION INC DBA RMEF',)})
        try:
            queries=c.wv_preferred_query_variants('Rocky Mountain Elk Foundation','810421425')
            self.assertEqual(c.normalized_match_name(queries[0]),c.normalized_match_name('Rocky Mountain Elk Foundation'))
            self.assertTrue(any('DBA' in query for query in queries))
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

    def test_ar_long_generic_leading_name_has_literal_completion_probe(self):
        name='Association of Graduates of the United States Air Force Academy'
        alias='THE ASSOCIATION OF GRADUATES OF THE UNITED STATES AIR FORCE ACADEMY'
        token=c.REVIEWED_NAME_CONTEXT.set({'840580665':(alias,)})
        try:
            queries,mapping=c.ar_reviewed_search_plan(c.checker.Organization(name,'840580665'),[name,alias])
            prefix='THE ASSOCIATION OF GRADUATES OF THE UNITED'
            self.assertIn(prefix,queries);self.assertIn(alias,mapping[prefix.casefold()])
            self.assertIn(alias,c.ar_completed_empty_identities([prefix],mapping))
            self.assertNotIn(alias,c.ar_completed_empty_identities([],mapping))
        finally:c.REVIEWED_NAME_CONTEXT.reset(token)

if __name__=='__main__':unittest.main(verbosity=2)
