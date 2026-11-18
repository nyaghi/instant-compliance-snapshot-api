"""Seventy distinct recorded organization inputs per changed state, offline.

Contract/edge-case controls use those inputs; they are not 350 new live checks.
Recorded failing source PDFs and state labels are tested separately below.
"""
import io
import json
import re
import socket
import time
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import registry_snapshot_server as c
from deployment import gate52_repairs as fix, source_visual_adapters as ca
from deployment.state_snapshots import DEADLINE
from reportlab.pdfgen.canvas import Canvas

P = Path(__file__).parent / 'fixtures/gate52'
CASES = json.loads((P/'STATE-70.json').read_text(encoding='utf-8'))
CHECKS = []


def record(state, case, scenario):
    CHECKS.append(dict(state=state, organization=case['name'], ein=case['ein'], scenario=scenario, passed=True))


def certificate(name, ein, *, adverse=False):
    output=io.BytesIO(); p=Canvas(output)
    p.drawString(30,740,'RENEWAL CERTIFICATE OF REGISTRATION')
    p.drawString(30,710,'Registration of '+name)
    p.drawString(30,680,'has been filed and will expire on September 23, 2027.')
    if adverse:p.drawString(30,650,'REVOKED')
    p.save();return output.getvalue()


def irs_return(name, ein, *, narrative=False, foreign=False):
    output=io.BytesIO();p=Canvas(output,pagesize=(612,792));p.drawString(30,740,'Electronic signature cover');p.showPage()
    p.drawString(30,750,'Return of Organization Exempt From Income Tax')
    p.drawString(86,710,'C Name of organization');p.drawString(430,710,'D Employer identification number')
    p.setFont('Helvetica',min(8,8*310/max(310,p.stringWidth(name,'Helvetica',8))));p.drawString(94,670,name)
    p.setFont('Helvetica',8);p.drawString(432,658,ein if not foreign else '99-9999999')
    p.showPage();p.setFont('Helvetica',min(7,7*570/max(570,p.stringWidth('Form 990 (2024) '+name+' '+ein+' Page 2','Helvetica',7))))
    p.drawString(20,770,'Form 990 (2024) '+name+' '+ein+' Page 2')
    if narrative:p.showPage();p.drawString(30,740,'Schedule O '+name+' '+ein)
    p.save();return output.getvalue()


class Gate52(unittest.TestCase):
    def setUp(self):
        self.guard=patch.object(socket.socket,'connect',side_effect=AssertionError('Offline tests forbid network'))
        self.guard.start()
    def tearDown(self):self.guard.stop()

    def test_CA_70_exempt_credential_and_identity_guards(self):
        self.assertEqual(len({case['ein'] for case in CASES}),70)
        for i,case in enumerate(CASES):
            entity=dict(id=5000000+i, entityStatus='Exempt',entityName=case['name'],fein=case['ein'])
            raffle=[dict(registrationType='Raffle',registrationNumber='RF123',registrationStatus='Expired')]
            result=c.checker.ca_evoke_status_from_record(entity,raffle)
            self.assertEqual((result[0],result[2],result[3]),('Exempt',str(entity['id']),None))
            run=NS(state='CA',ein=case['ein'],source_detail_hints={})
            run.remember_detail=lambda ident,name,url:run.source_detail_hints.update({ident:dict(url=url)})
            row=NS(success=True,status='Exempt',matched_registry_name=case['name'],matched_registry_identifier=result[2],
                   raw_status_text=result[1],_cc_selected_entity=entity,_cc_registration_records=raffle)
            ca.remember_ca_exempt_entity(run,row);self.assertIn(result[2],run.source_detail_hints)
            entity['fein']='999999999';run.source_detail_hints={};ca.remember_ca_exempt_entity(run,row)
            self.assertEqual(run.source_detail_hints,{})
            for bad in [dict(raffle[0],registrationType='Unknown'),dict(raffle[0],registrationStatus='Revoked'),
                        dict(raffle[0],registrationType='Charitable Organization')]:
                self.assertFalse(fix.ca_exempt_raffle_only(entity,[bad]))
            record('CA',case,'entity exemption, original ID, foreign EIN and non-raffle safeguards')

    def test_GA_70_complete_compound_labels_review_and_foreign_EIN(self):
        for case in CASES:
            target=case['name'];label=target+', Separately Printed Trade Name'
            expected=len(c.distinctive_match_tokens(target))>=2
            self.assertEqual(fix.ga_compound_candidate(c,[target],label),expected)
            self.assertFalse(fix.ga_compound_candidate(c,[target],target+' Regional Foundation'))
            self.assertFalse(fix.ga_compound_candidate(c,[target],'Unrelated Regional Foundation'))
            org=c.checker.Organization(target,case['ein'])
            row=dict(name=label,ein='',identifier='CH123456',_ga_compound_candidate=True)
            with patch.object(c,'known_names_for_ein',return_value=[]),patch.object(c,'user_rejected_credential',return_value=False), \
                 patch.object(c,'licensed_charity_foreign_ein',return_value={}),patch.object(c,'licensed_charity_street_evidence',return_value={}):
                if expected:self.assertEqual(c.licensed_charity_identity(org,row,'GA',time.monotonic()+3),'possible')
                foreign=dict(row,ein='999999999')
                self.assertEqual(c.licensed_charity_identity(org,foreign,'GA',time.monotonic()+3),'rejected')
            record('GA',case,'complete delimited name is review-only; affiliate suffix and foreign EIN excluded')

    def test_OK_70_printed_dates_and_adverse_or_wrong_name(self):
        for case in CASES:
            raw=certificate(case['name'],case['ein'])
            self.assertEqual(c.ok_certificate_expiration(raw,case['name'],first_page_only=True)[0],date(2027,9,23))
            self.assertIsNone(c.ok_certificate_expiration(raw,'UNRELATED ORGANIZATION',first_page_only=True)[0])
            self.assertIsNone(c.ok_certificate_expiration(certificate(case['name'],case['ein'],adverse=True),case['name'],first_page_only=True)[0])
            self.assertIsNone(c.ok_certificate_expiration(raw,case['name'],deadline=0,first_page_only=True)[0])
            record('OK',case,'original certificate text, wrong identity, adverse evidence and exhausted budget')

    def test_MA_70_primary_header_identity_not_narrative(self):
        for case in CASES:
            ein=case['ein'][:2]+'-'+case['ein'][2:]
            raw=irs_return(case['name'],ein)
            self.assertTrue(fix.ma_primary_return_identity(raw,case['name'],case['ein'],time.monotonic()+4))
            self.assertFalse(fix.ma_primary_return_identity(raw,'UNRELATED ORGANIZATION',case['ein'],time.monotonic()+4))
            self.assertFalse(fix.ma_primary_return_identity(irs_return(case['name'],ein,foreign=True),case['name'],case['ein'],time.monotonic()+4))
            self.assertFalse(fix.ma_primary_return_identity(raw,case['name'],case['ein'],0))
            record('MA',case,'cover + primary Form990 fields and adjacent page2; conflicting filer rejected')

    def test_NJ_70_registered_name_source_anomalies(self):
        for case in CASES:
            primary=dict(name=case['name'],verified=True,evidence=[dict(source='New Jersey',type='Registered name')])
            other=dict(name='Unrelated Distinctive Enterprise',verified=True,evidence=[dict(source='New Jersey',type='Registered name')])
            sources=[dict(source='NJ',complete=True,names=[primary,other]),dict(source='IRS',complete=True,names=[primary])]
            self.assertIn(c.identity_name_key(other['name']),fix.nj_discovery_discrepancies(c,[primary,other],sources,case['name']))
            for safe in [dict(other,historical=True),dict(other,evidence=other['evidence']+[dict(source='IRS',type='Former name')]),
                         dict(other,evidence=[dict(source='New Jersey',type='AKA / DBA')])]:
                self.assertFalse(fix.nj_discovery_discrepancies(c,[primary,safe],sources,case['name']))
            self.assertFalse(fix.nj_discovery_discrepancies(c,[primary,other],sources[:1],case['name']))
            record('NJ',case,'sole NJ unrelated registered name unchecked; independently supported and historical aliases retained')

    def test_recorded_source_MA_OK(self):
        raw=(P/'MA-GETTYSBURG-2025-FEDERAL.pdf').read_bytes()
        self.assertTrue(fix.ma_primary_return_identity(raw,'Gettysburg College','231352641',time.monotonic()+4))
        self.assertFalse(fix.ma_primary_return_identity(raw,'Gettysburg College','750801250',time.monotonic()+4))
        response=NS(ok=True,body=lambda:raw);url='https://masscharities.my.site.com/FilingSearch/sfc/servlet.shepherd/document/download/069000000000000'
        completed=dict(filings={'053340':dict(complete=True,documents=[dict(year='2025',title='Form-PC Data'),dict(year='2025',title='Federal Revenue Support.pdf',url=url)])},registration_documents={'053340':dict(complete=True)})
        token=DEADLINE.set(time.monotonic()+20)
        try:
            value=c.ma_confirm_filing_attachment(NS(request=NS(get=lambda *a,**k:response)),c.checker.Organization('Gettysburg College','231352641'),completed,dict(ago_account='053340',name='Gettysburg College',source_tax_id='75-080125'))
            self.assertEqual(value['filing_year'],2025)
        finally:DEADLINE.reset(token)
        for doc in ['78643640002.pdf','78643650002.pdf']:
            t=time.monotonic();due,text=c.ok_certificate_expiration((P/doc).read_bytes(),'FOOD BANK FOR NEW YORK CITY',deadline=t+10,first_page_only=True)
            self.assertEqual(due,date(2027,9,23));self.assertLess(time.monotonic()-t,10)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Gate52)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    (P/'LOCAL-RESULTS.json').write_text(json.dumps(dict(checks=CHECKS,tests=result.testsRun,failures=len(result.failures),errors=len(result.errors)),indent=2),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
