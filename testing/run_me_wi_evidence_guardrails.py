"""Queue admission and generic, live financial identity controls; no real-EIN allowlist."""
import copy
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.ein = '12-3456789'
        self.name = 'Regional Learning Association Foundation'
        self.candidate = c.wi_foundation_identity_review('Regional Learning Association', self.name,
            '76543-800', 'CredSummaryDetails.aspx?chid=765432&h=123456789', '12/31/2027')
        self.detail = ('Name: Regional Learning Association Credential Type: Charitable Organization '
                       'Credential Number: 76543-800 Status License is current (Active)')
        self.amounts = (' CONTRIBUTIONS $120,000.00 OTHER REVENUE ($400.00) MANAGEMENT $7,000.00 '
            'PROGRAM SERVICE(S) $3,000.00 FUND RAISING $1,000.00 PAYMENT(S) TO AFFILIATE $0.00 '
            'NET WORTH AT END $115,000.00 OTHER CHANGES(S) IN NET WORTH $6,400.00 ')
        self.filing = {'ein':123456789,'formtype':1,'tax_prd':202412,'totcntrbs':120000,
            'totrevenue':119600,'totfuncexpns':11000,'totnetassetsend':115000,'othrchgsnetassetfnd':6400}
        self.profile = {'organization':{'ein':123456789},'filings_with_data':[self.filing]}
        self.form = self.detail + '<input type="hidden" name="__VIEWSTATE" value="test" /><option value="2024">2024</option>'
        self.response = self.detail + '<option selected="selected" value="2024">2024</option>' + self.amounts

    def retrieve(self, *, profile=None, form=None, response=None):
        diagnostics = {}
        with patch.object(c,'public_profile_for_ein',return_value=profile if profile is not None else self.profile), \
             patch.object(c,'wi_identity_page',side_effect=[form or self.form,response or self.response]):
            evidence=c.wi_foundation_filing_identity(self.candidate,self.name,self.ein,time.monotonic()+30,diagnostics)
        return evidence,diagnostics

    def test_generic_same_ein_five_amount_identity(self):
        proof,diag=self.retrieve()
        self.assertEqual(proof['credential'],'76543-800')
        self.assertEqual(proof['fiscal_year'],'2024')
        self.assertEqual(proof['matched_amounts']['totrevenue'],119600)
        self.assertTrue(c.wi_reviewed_credential_identity(self.name,self.ein,dict(self.candidate,reviewed_identity_evidence=proof)))

    def test_latest_common_year_not_latest_irs_year(self):
        profile=copy.deepcopy(self.profile)
        profile['filings_with_data'].insert(0,dict(self.filing,tax_prd=202512,totrevenue=1))
        proof,_=self.retrieve(profile=profile)
        self.assertEqual(proof['tax_period'],'202412')

    def test_conflicting_or_missing_ein_fails_closed(self):
        for location in ['organization','filing']:
            for ein in [None,987654321]:
                profile=copy.deepcopy(self.profile)
                (profile['organization'] if location=='organization' else profile['filings_with_data'][0])['ein']=ein
                with self.subTest(location=location,ein=ein):self.assertFalse(self.retrieve(profile=profile)[0])

    def test_same_year_multiple_periods_are_not_guessed(self):
        profile=copy.deepcopy(self.profile)
        profile['filings_with_data'].append(dict(self.filing,tax_prd=202406))
        self.assertFalse(self.retrieve(profile=profile)[0])

    def test_actual_selected_year_and_credential_required(self):
        for page in [self.response.replace('value="2024"','value="2023"'),
                     self.response.replace('selected="selected"',''),
                     self.response.replace('76543-800','99999-800'),
                     self.response.replace('Regional Learning Association','Regional Learning Chapter'),
                     self.response.replace('$120,000.00','$120,001.00'),
                     self.response.replace('$120,000.00','$120,000.50'),
                     self.response+' CONTRIBUTIONS $120,000.00']:
            with self.subTest(page=page):self.assertFalse(self.retrieve(response=page)[0])

    def test_zero_or_missing_values_are_not_identity_proof(self):
        for key in ['totcntrbs','totfuncexpns','othrchgsnetassetfnd']:
            filing=dict(self.filing);filing.pop(key)
            self.assertFalse(c.wi_990ez_corresponding_amounts(self.amounts,filing))
        zeros=c.re.sub(r'\(?\$[\d,]+\.00\)?','$0.00',self.amounts)
        self.assertFalse(c.wi_990ez_corresponding_amounts(zeros,{k:0 for k in self.filing}))

    def test_credential_or_requested_ein_cannot_change_after_proof(self):
        proof,_=self.retrieve()
        for changes in [{'license_number':'99999-800'}, {'registry_name':'Regional Learning Chapter'},
                        {'detail_href':'CredSummaryDetails.aspx?chid=1'},
                        {'detail_href':'https://example.com/CredSummaryDetails.aspx?chid=765432'}]:
            candidate=dict(self.candidate,reviewed_identity_evidence=proof,**changes)
            self.assertFalse(c.wi_reviewed_credential_identity(self.name,self.ein,candidate))
        self.assertFalse(c.wi_reviewed_credential_identity(self.name,'98-7654321',dict(self.candidate,reviewed_identity_evidence=proof)))

    def test_live_status_recovers_once_without_changing_identity(self):
        proof,_=self.retrieve()
        with patch.object(c,'wi_foundation_filing_identity',return_value=proof), \
             patch.object(c,'wi_identity_page',side_effect=['Loading',self.detail.replace('(Active)','(Revoked)')]) as fetch:
            candidate=c.wi_confirm_reviewed_credential(self.candidate,self.name,self.ein)
        self.assertFalse(candidate['identity_conflict'])
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(c.wi_status_from_detail_status(candidate['detail_status']),'Revoked')

    def test_missing_live_detail_cannot_freeze_old_status(self):
        proof,_=self.retrieve()
        with patch.object(c,'wi_foundation_filing_identity',return_value=proof),patch.object(c,'wi_identity_page',return_value='Loading'):
            self.assertTrue(c.wi_confirm_reviewed_credential(self.candidate,self.name,self.ein)['identity_conflict'])

    def test_maine_wait_reserves_its_search_time(self):
        with patch.object(c.time,'perf_counter',return_value=0):
            self.assertEqual(c.me_lane_wait_seconds(265),160)
            self.assertEqual(c.me_lane_wait_seconds(190),85)
            self.assertEqual(c.me_lane_wait_seconds(100),0)

    def test_maine_can_start_after_a_105_second_predecessor(self):
        now=[0.0];lock=Mock()
        def acquire(timeout):
            self.assertEqual(timeout,160)
            now[0]=110
            return True
        lock.acquire.side_effect=acquire
        with patch.object(c.time,'perf_counter',side_effect=lambda:now[0]),patch.object(c,'ME_LOOKUP_LOCK',lock), \
             patch.object(c,'run_state_lookup',return_value={'status':'Current'}) as lookup:
            result=c.run_me_lookup_with_lane('Example Charity','123456789',{'deadline':265})
        lookup.assert_called_once();lock.release.assert_called_once()
        self.assertEqual(result['me_queue_seconds'],110)

    def test_maine_failed_query_diagnostics_do_not_become_a_negative(self):
        org=c.checker.Organization('Example Charity','123456789')
        org._cc_me_progress={'completed':set()}
        transport=Mock();transport.stage='name search POST';transport.search.side_effect=TimeoutError('source timed out')
        with patch.object(c,'MaineRegistrySession',return_value=transport), \
             patch.object(c,'me_fast_direct_query_variants',return_value=['Example Charity']):
            self.assertIsNone(c.me_fast_direct_confirmation_result(org))
        attempts=org._cc_me_progress['source_attempts']
        self.assertEqual(attempts[0]['stage'],'name search POST')
        self.assertFalse(attempts[0]['complete'])
        self.assertFalse(org._cc_me_progress['completed'])


if __name__=='__main__':unittest.main(verbosity=2)
