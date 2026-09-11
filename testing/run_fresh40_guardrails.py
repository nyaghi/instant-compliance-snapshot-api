"""Reported identity and fiscal-period regressions with independent counterexamples."""
import sys, time, unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c

class AsOf(date):
    @classmethod
    def today(cls):return cls(2026,9,11)

class CalendarTests(unittest.TestCase):
    def test_leap_and_nonleap_recurrence(self):
        for year,day in [(2024,29),(2025,28),(2026,28),(2028,29)]:
            self.assertEqual(c.fiscal_period_end_in_year(year,(2,29)),date(year,2,day))
            self.assertEqual(c.filing_due_date_options('KY',year,(2,29))['base_due'],date(year,7,15))
        for period in [(12,31),(6,30),(2,28)]:
            for year in [2024,2025,2026,2028]:self.assertEqual(c.fiscal_period_end_in_year(year,period),date(year,*period))
    def test_invalid_dates_not_coerced(self):
        for period in [(2,30),(4,31),(13,1),(0,1),(2,0)]:
            with self.assertRaises(c.FiscalPeriodError):c.fiscal_period_end_in_year(2026,period)
    def test_latest_period_compares_month_not_just_year_or_extraction(self):
        profile={'filings_with_data':[{'tax_prd':202402,'tax_prd_yr':2024}],
                 'filings_without_data':[{'tax_prd':202412,'tax_prd_yr':2024,'formtype_str':'990'}]}
        with patch.object(c,'public_profile_for_ein',return_value=profile):
            self.assertEqual(c.public_profile_latest_tax_period_for_ein('237110058'),(2024,(12,31)))
            self.assertEqual(c.fiscal_year_end_for_ein('237110058'),(12,31))
    def test_profile_header_uses_full_chronology(self):
        with patch.object(c,'public_profile_for_ein',return_value={'organization':{'tax_period':'2025-06-01'},'filings_with_data':[{'tax_prd':202412}]}):
            self.assertEqual(c.public_profile_latest_tax_period_for_ein('123456789'),(2025,(6,30)))
    def test_year_label_does_not_change_february_to_december(self):
        with patch.object(c,'public_profile_for_ein',return_value={'filings_with_data':[{'tax_prd':202402,'tax_prd_yr':2024}]}):
            self.assertEqual(c.public_profile_latest_tax_period_for_ein('123456789'),(2024,(2,29)))
    def test_supplemental_and_malformed_periods_do_not_win(self):
        profile={'filings_with_data':[{'tax_prd':202406}], 'filings_without_data':[{'tax_prd':202412,'formtype_str':'990-T'}, {'tax_prd':202599}]}
        with patch.object(c,'public_profile_for_ein',return_value=profile):
            self.assertEqual(c.public_profile_latest_tax_period_for_ein('123456789'),(2024,(6,30)))
    def test_profile_failure_preserves_existing_fallback(self):
        with patch.object(c,'public_profile_for_ein',return_value={}),patch.object(c,'fiscal_period_for_ein',return_value=(None,date(2025,9,30))):
            self.assertEqual(c.fiscal_year_end_for_ein('123456789'),(9,30))
    def test_state_period_and_filed_year_take_precedence(self):
        result=c.checker.StateResult('Example Foundation','123456789','KY','Current','')
        result.raw_status_text='Yr Last Filed: 2024';result.fiscal_year_end='6/30/2024'
        with patch.object(c,'public_profile_for_ein',return_value={'filings_with_data':[{'tax_prd':202512}]}),patch.object(c,'fiscal_period_for_ein',return_value=(None,None)):
            context=c.filing_context(result,'Yr Last Filed: 2024')
        self.assertEqual(context['represented_year'],2024)
        self.assertEqual(context['fiscal_end'],(6,30))
        self.assertEqual(context['base_due_date'],date(2025,11,15))
    def test_explicit_date_states_do_not_construct_fiscal_date(self):
        with patch.object(c,'fiscal_period_end_in_year',side_effect=AssertionError('irrelevant fiscal calculation')):
            for state in ['OH','OK']:
                self.assertIsNone(c.filing_due_date_options(state,2026,(2,29))['base_due'])
    def test_final_calculation_failure_is_inconclusive(self):
        org=c.checker.Organization('Example Foundation','123456789')
        result=c.checker.StateResult(org.organization_name,org.ein,'KY','Current','')
        result.success=True
        with patch.object(c,'true_status_from_body',side_effect=c.FiscalPeriodError()),patch.object(c,'public_profile_for_ein',return_value={}):
            data=c.response_data_for_lookup(result,'',org,org.organization_name,org.ein,'KY',time.perf_counter())
        self.assertEqual(data['status'],'Unable to Confirm');self.assertFalse(data['success'])
        self.assertEqual(data['reason_code'],'FISCAL_PERIOD_UNCONFIRMED')
    def test_caught_calculation_error_not_reported_as_outage(self):
        org=c.checker.Organization('Example Foundation','123456789')
        result=c.checker.StateResult(org.organization_name,org.ein,'MD','Site Not Reachable','')
        result.error='Fiscal period could not be interpreted from the available date evidence'
        with patch.object(c,'public_profile_for_ein',return_value={}):
            data=c.response_data_for_lookup(result,'',org,org.organization_name,org.ein,'MD',time.perf_counter())
        self.assertEqual(data['status'],'Unable to Confirm');self.assertFalse(data['success'])

class FloridaTests(unittest.TestCase):
    def lookup(self,requested,candidate):
        page=MagicMock();page.expect_navigation.return_value.__enter__.return_value.value=Mock(status=200)
        page.evaluate.return_value=[{'text':f'Business Name {candidate} License/Registration Number CH50812 Status Active Expiration Date 2/13/2027','index':0}]
        with patch.object(c,'high_signal_search_phrases',return_value=[requested]),patch.object(c,'organization_name_variants',return_value=[requested,'Air Force Academy'] if requested=='Air Force Academy Foundation' else [requested]),patch.object(c.checker,'find_visible_input',return_value=page),patch.object(c,'readable_page_text',return_value='Search results CH50812'),patch.object(c,'registry_candidate_fields',return_value={'status':'Active'}),patch.object(c.time,'sleep'):
            return c.search_fl(page,SimpleNamespace(organization_name=requested,ein='260537053'))
    def test_foundation_does_not_match_athletic_corporation(self):
        r=self.lookup('Air Force Academy Foundation','AIR FORCE ACADEMY ATHLETIC CORPORATION')
        self.assertEqual(c.public_status(r),'Not Registered');self.assertFalse(r.matched_registry_name)
    def test_exact_athletic_corporation_is_still_allowed(self):
        r=self.lookup('Air Force Academy Athletic Corporation','AIR FORCE ACADEMY ATHLETIC CORPORATION')
        self.assertTrue(r.success);self.assertEqual(r.matched_registry_identifier,'CH50812')
    def test_full_foundation_with_entity_suffix_is_allowed(self):
        r=self.lookup('Air Force Academy Foundation','AIR FORCE ACADEMY FOUNDATION, INC.')
        self.assertTrue(r.success);self.assertIn('FOUNDATION',r.matched_registry_name)

class MinnesotaTests(unittest.TestCase):
    name='Albert Einstein College of Medicine'
    row={'index':0,'text':'Montefiore Medical Center Albert Einstein College of Medicine',
         'href':'CHR_GeneralInfo.asp?FederalID=131740114&Yr=CURR&cmdSearch=View','linkText':'Montefiore Medical Center','aliases':[name]}
    def lookup(self,rows=None,detail_aliases=None,detail_ein='131740114',click_failure=False):
        page=MagicMock();page.url='https://www.ag.state.mn.us/Charity/Search/'+self.row['href']
        page.evaluate.return_value=rows if rows is not None else [dict(self.row)]
        page.locator.return_value.all_inner_texts.return_value=[self.name] if detail_aliases is None else detail_aliases
        if click_failure:page.locator.return_value.first.click.side_effect=TimeoutError('detail unavailable')
        detail=f'FEDERAL ID# {detail_ein}\nMontefiore Medical Center\nStatus Active\nExtension Granted\nFinancial Information\nFor Fiscal Year Ending 12/31/2024'
        with patch.object(c,'build_search_queries',return_value=[self.name]),patch.object(c.checker,'find_visible_input',return_value=Mock()),patch.object(c.checker,'safe_wait_for_network_idle'),patch.object(c,'readable_page_text',side_effect=['No results found','No results found','Search result',detail]),patch.object(c.time,'sleep'),patch.object(c,'date',AsOf):
            r=c.search_mn(page,c.checker.Organization(self.name,'83-0621846'))
        return r,page
    def test_exact_state_alias_under_other_ein_is_confirmed(self):
        r,page=self.lookup();self.assertTrue(r.success)
        self.assertEqual(c.public_status(r),'Delinquent')
        self.assertEqual(r.mn_alias_evidence['registered_ein'],'13-1740114')
        self.assertEqual(r.ein,'83-0621846');self.assertEqual(r.queries_attempted,[self.name])
        self.assertIn('not a separate registration',r.source_note)
        page.get_by_role.assert_called_with('button',name='Alternate Name(s)',exact=True)
        with patch.object(c,'public_profile_for_ein',return_value={}):
            data=c.response_data_for_lookup(r,'',c.checker.Organization(self.name,r.ein),self.name,r.ein,'MN',time.perf_counter())
        self.assertIn('alternate name under Montefiore',data['comments'])
        self.assertIn('not a separate registration',data['comments'])
        self.assertEqual(__import__('json').loads(data['debug_trace'])['accepted_candidate']['reason'],'MATCH_STATE_CONFIRMED_ALTERNATE_NAME')
        r.state='FL';self.assertFalse(c.mn_confirmed_alias_evidence(r))
    def test_different_ein_without_structured_alias_is_rejected(self):
        r,_=self.lookup([{**self.row,'aliases':[]}]);self.assertEqual(c.public_status(r),'Not Registered')
        self.assertIn('name searches',r.source_note)
    def test_similar_alias_is_not_exact(self):
        self.assertFalse(c.mn_exact_structured_alias([self.name+' Foundation'],self.name))
    def test_detail_must_confirm_alias(self):
        r,_=self.lookup(detail_aliases=[]);self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)
    def test_detail_must_confirm_registered_ein(self):
        r,_=self.lookup(detail_ein='999999999');self.assertEqual(r.status,'Unable to Confirm')
    def test_unavailable_alias_detail_is_not_negative(self):
        r,_=self.lookup(click_failure=True);self.assertEqual(r.status,'Unable to Confirm')
    def test_conflicting_alias_registrations_are_not_first_selected(self):
        r,_=self.lookup([self.row,{**self.row,'href':self.row['href'].replace('131740114','999999999')}])
        self.assertEqual(r.status,'Unable to Confirm');self.assertFalse(r.success)

class NewYorkVerificationTests(unittest.TestCase):
    def page(self, verified=False, accepted=True):
        page=MagicMock();search=MagicMock();search.is_enabled.return_value=verified
        verify=MagicMock()
        page.get_by_role.side_effect=lambda role,**kw: search if kw.get('name')=='Search' else verify
        responses=[]
        for status,payload in ([(200 if accepted else 401,{'verified':accepted})] if not verified else [])+[(200,{'success':True,'statusCode':200,'data':[]})]:
            response=Mock(status=status);response.json.return_value=payload
            pending=MagicMock();pending.__enter__.return_value.value=response;responses.append(pending)
        page.expect_response.side_effect=responses
        return page,search,verify
    def test_normal_verify_precedes_fresh_completed_search(self):
        page,search,verify=self.page()
        response=c.ny_browser_registry_response(page,'RegistrySearch',{'ein':'860481941'},12)
        self.assertEqual(response.json()['data'],[])
        verify.click.assert_called_once();search.click.assert_called_once()
        predicate=page.expect_response.call_args_list[-1].args[0]
        self.assertTrue(predicate(Mock(url='https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?ein=860481941&token=test')))
        self.assertTrue(predicate(Mock(url='https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?ein=86-0481941&token=test')))
        self.assertFalse(predicate(Mock(url='https://charities-search-api.ag.ny.gov/api/FileNet/RegistrySearch?ein=841267604&token=test')))
    def predicate(self, params):
        page,_,_=self.page(verified=True)
        c.ny_browser_registry_response(page,'RegistrySearch',params,12)
        return page.expect_response.call_args.args[0]
    def test_ein_response_rejects_wrong_malformed_missing_and_duplicate_queries(self):
        predicate=self.predicate({'ein':'860481941'})
        for query in ['ein=84-1267604','ein=86048194','ein=8604819410','ein=xx860481941',
                      'ein=86--0481941','orgName=Make+A+Wish','ein=',
                      'ein=860481941&ein=841267604','ein=860481941&ein=860481941']:
            with self.subTest(query=query):
                self.assertFalse(predicate(Mock(url=c.NY_REGISTRY_API+'/RegistrySearch?'+query)))
    def test_ein_format_does_not_relax_official_host_or_endpoint(self):
        predicate=self.predicate({'ein':'860481941'})
        for url in ['https://example.com/api/FileNet/RegistrySearch?ein=86-0481941',
                    c.NY_REGISTRY_API+'/RegistryDetail?ein=86-0481941']:
            self.assertFalse(predicate(Mock(url=url)))
    def test_formatted_expected_ein_accepts_same_digits_only(self):
        predicate=self.predicate({'ein':'86-0481941'})
        self.assertTrue(predicate(Mock(url=c.NY_REGISTRY_API+'/RegistrySearch?ein=860481941')))
        self.assertFalse(predicate(Mock(url=c.NY_REGISTRY_API+'/RegistrySearch?ein=237110058')))
    def test_ein_normalization_does_not_relax_other_search_fields(self):
        predicate=self.predicate({'ein':'860481941','orgName':'Make A Wish'})
        self.assertTrue(predicate(Mock(url=c.NY_REGISTRY_API+'/RegistrySearch?ein=86-0481941&orgName=Make+A+Wish')))
        self.assertFalse(predicate(Mock(url=c.NY_REGISTRY_API+'/RegistrySearch?ein=86-0481941&orgName=Other+Name')))
    def test_name_fallback_rejects_retained_ein_or_unrequested_filters(self):
        predicate=self.predicate({'orgName':'Achieving the Dream'})
        base=c.NY_REGISTRY_API+'/RegistrySearch?orgName=Achieving+the+Dream'
        self.assertTrue(predicate(Mock(url=base)))
        for extra in ['ein=27-1635830','orgID=50-28-64','state=NY','city=Albany','regtype=NFP']:
            with self.subTest(extra=extra):
                self.assertFalse(predicate(Mock(url=base+'&'+extra)))
    def test_failed_verification_never_searches_or_claims_negative(self):
        page,search,verify=self.page(accepted=False)
        with self.assertRaises(c.NYVerificationRequired):c.ny_browser_registry_response(page,'RegistrySearch',{'ein':'860481941'},12)
        search.click.assert_not_called()
    def test_verified_session_still_submits_each_query(self):
        page,search,verify=self.page(verified=True)
        c.ny_browser_registry_response(page,'RegistrySearch',{'orgName':'Example Relief'},12)
        verify.click.assert_not_called();search.click.assert_called_once()
    def test_verification_failure_survives_final_response(self):
        org=c.checker.Organization('Make-A-Wish Foundation of America','86-0481941')
        with patch.object(c,'ny_browser_registry_response',side_effect=c.NYVerificationRequired('Verification rejected')):
            result=c.search_ny_direct(org,browser_page=Mock())
        self.assertEqual(result.status_reason,'NY_VERIFICATION_REQUIRED')
        with patch.object(c,'public_profile_for_ein',return_value={}):
            data=c.response_data_for_lookup(result,'',org,org.organization_name,org.ein,'NY',time.perf_counter())
        self.assertEqual(data['status'],'Unable to Confirm');self.assertFalse(data['success'])

class MassachusettsPeriodTests(unittest.TestCase):
    def form(self,start,end,account='082771',status='Submitted'):
        return {'period_start':start,'period_end':end,'filing_year':2024,'ago_account':account,'filing_status':status}
    def test_short_transition_period_wins_in_either_row_order(self):
        first=self.form('3/1/2023','2/28/2024');last=self.form('3/1/2024','12/31/2024')
        for forms in [[first,last],[last,first]]:
            r=c.ma_latest_distinct_fiscal_period(forms)
            self.assertEqual(r['period_end'],'12/31/2024');self.assertEqual(r['same_year_periods_reviewed'],2)
    def test_conflicts_missing_periods_and_foreign_accounts_stay_inconclusive(self):
        first=self.form('3/1/2023','2/28/2024')
        for second in [dict(first),self.form('1/1/2024','12/31/2024'),self.form('','12/31/2024'),self.form('3/1/2024','12/31/2024','99999'),self.form('3/1/2024','12/31/2024',status='Draft'),{}]:
            self.assertFalse(c.ma_latest_distinct_fiscal_period([first,second]))
    def test_browser_reads_both_forms_and_closes_each(self):
        page=MagicMock();page.get_by_role.return_value.all_inner_texts.return_value=['2024 Form-PC Data','2024 Form-PC Data']
        details=[];popups=[]
        for start,end in [('3/1/2023','2/28/2024'),('3/1/2024','12/31/2024')]:
            detail=MagicMock();detail.url='https://masscharities.my.site.com/FilingSearch/s/detail/fixture'+end
            detail.locator.return_value.inner_text.return_value=f'AG Charity Number 082771 Filing Year 2024 Filing Status Submitted Current Fiscal Period Start Date {start} Current Fiscal Period End Date {end}'
            pending=MagicMock();pending.__enter__.return_value.value=detail;popups.append(pending);details.append(detail)
        page.expect_popup.side_effect=popups
        with patch.object(c,'date',AsOf):r=c.ma_read_latest_form_pc(page,None,'AG Account Number 082771')
        self.assertEqual(r['period_end'],'12/31/2024')
        for detail in details:detail.close.assert_called_once()

if __name__=='__main__':unittest.main(verbosity=2)
