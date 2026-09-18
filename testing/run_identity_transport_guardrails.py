"""Direct public-page transport must preserve browser names and entity binding."""
import copy,json,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import registry_snapshot_server as c
F=Path(__file__).parent/'fixtures/pa-identity-transport'

class PennsylvaniaTransport(unittest.TestCase):
    def fixture(self,ein='050536854'):
        return json.loads((F/(ein+'.json')).read_text())
    def run_fixture(self,fixture):
        with patch.object(c,'identity_fetch',side_effect=[json.dumps(r).encode() for r in fixture['responses']]) as fetch:
            result=c.identity_pa_names(fixture['ein'],time.monotonic()+30)
        for call in fetch.call_args_list:
            self.assertEqual(call.args[0],'https://www.charities.pa.gov/api/Charities/Search')
        return result
    def test_six_browser_parity_controls_including_empty_and_former_names(self):
        for file in F.glob('[0-9]*.json'):
            with self.subTest(file=file.name):
                fixture=json.loads(file.read_text());result=self.run_fixture(fixture)
                self.assertTrue(result['complete'])
                self.assertEqual({c.identity_name_key(n['name']) for n in result['names']},{c.identity_name_key(n) for n in fixture['expected_names']})
    def test_search_different_ein_cannot_supply_legal_or_alias_names(self):
        fixture=self.fixture();fixture['responses'][0]['Table'][0]['EIN']='999999999'
        result=self.run_fixture(fixture)
        self.assertFalse(result['complete']);self.assertEqual(result['names'],[])
    def test_detail_different_ein_cannot_supply_aliases(self):
        fixture=self.fixture();fixture['responses'][1]['Table'][0]['EIN']='999999999'
        result=self.run_fixture(fixture)
        self.assertFalse(result['complete']);self.assertEqual(len(result['names']),1)
    def test_conflicting_same_person_ein_blocks_aliases(self):
        fixture=self.fixture();bad=copy.deepcopy(fixture['responses'][1]['Table'][0]);bad['EIN']='999999999';fixture['responses'][1]['Table'].append(bad)
        result=self.run_fixture(fixture)
        self.assertFalse(result['complete']);self.assertEqual(len(result['names']),1)
    def test_alias_from_other_person_or_officer_is_never_used(self):
        fixture=self.fixture();fixture['responses'][1]['Table1'] += [dict(PersonId=0,Fullname='Wrong Chapter',NameTypeName='Other Name'),dict(PersonId=fixture['responses'][0]['Table'][0]['PersonId'],Fullname='Wrong Officer',NameTypeName='Officer')]
        result=self.run_fixture(fixture)
        self.assertTrue(result['complete']);self.assertFalse(any(n['name'].startswith('Wrong') for n in result['names']))
    def test_missing_additional_name_is_partial(self):
        fixture=self.fixture();fixture['responses'][1]['Table1']=[]
        result=self.run_fixture(fixture)
        self.assertFalse(result['complete']);self.assertEqual(len(result['names']),1)
    def test_missing_rows_is_not_complete_absence(self):
        fixture=self.fixture();fixture['responses'][0]['Table1'][0]['RESULTCOUNT']=20
        self.assertFalse(self.run_fixture(fixture)['complete'])
    def test_timeout_retains_only_confirmed_legal_name(self):
        fixture=self.fixture()
        with patch.object(c,'identity_fetch',side_effect=[json.dumps(fixture['responses'][0]).encode(),TimeoutError()]):
            result=c.identity_pa_names(fixture['ein'],time.monotonic()+30)
        self.assertFalse(result['complete']);self.assertEqual(len(result['names']),1)
    def test_pennsylvania_does_not_wait_for_browser_slot(self):
        c.IDENTITY_SOURCE_CACHE.clear()
        with patch.object(c,'identity_pa_names',return_value={'names':[],'complete':True}),patch.object(c,'identity_browser_names',side_effect=AssertionError('Browser invoked')):
            self.assertTrue(c.identity_source_result('PA','123456789',time.monotonic()+1)['complete'])
        self.assertNotIn('PA',c.IDENTITY_BROWSER_STATES)

class OtherPublicTransports(unittest.TestCase):
    def test_wa_returns_only_requested_ein_names_and_explicit_aliases(self):
        rows=json.loads((F/'wa-ywca.json').read_text())
        rows.append({'FEINNumber':'999999999','EntityName':'Wrong Chapter','AKANames':'Wrong DBA'})
        with patch.object(c,'identity_fetch',return_value=json.dumps(rows).encode()) as fetch:
            result=c.identity_wa_names('131624103',time.monotonic()+30)
        self.assertEqual({n['name'] for n in result['names']},{'YWCA USA, INC.','YWCA OF THE U.S.A.'})
        self.assertFalse(result['complete']);self.assertEqual(fetch.call_args.kwargs['request_timeout'],35)
    def test_wa_full_page_is_partial_not_empty_or_complete(self):
        row=json.loads((F/'wa-ywca.json').read_text())[0]
        with patch.object(c,'identity_fetch',return_value=json.dumps([row]*10).encode()):
            self.assertFalse(c.identity_wa_names('131624103',time.monotonic()+30)['complete'])
    def test_wa_complete_empty_response(self):
        with patch.object(c,'identity_fetch',return_value=b'[]'):
            result=c.identity_wa_names('131624103',time.monotonic()+30)
        self.assertTrue(result['complete']);self.assertEqual(result['names'],[])
    def test_oh_public_result_and_wrong_ein(self):
        source=(F/'oh-ywca.html').read_bytes()
        with patch.object(c,'identity_fetch',return_value=source):
            result=c.identity_oh_names('131624103',time.monotonic()+30)
            with self.assertRaises(ValueError):c.identity_oh_names('999999999',time.monotonic()+30)
        self.assertTrue(result['complete']);self.assertEqual(result['names'][0]['name'],'YWCA of the USA, National Board')
    def test_oh_unloaded_page_is_not_completed_empty_search(self):
        with patch.object(c,'identity_fetch',return_value=b'<h1>Research Charities</h1>'):
            with self.assertRaises(ValueError):c.identity_oh_names('131624103',time.monotonic()+30)
    def test_oh_incomplete_pagination_retains_names_but_is_partial(self):
        source=(F/'oh-ywca.html').read_text().replace('Page 1 of 1','Page 1 of 2')
        with patch.object(c,'identity_fetch',return_value=source.encode()):
            result=c.identity_oh_names('131624103',time.monotonic()+30)
        self.assertFalse(result['complete']);self.assertTrue(result['names'])
    def test_oh_completed_empty_search_requires_submitted_ein(self):
        source='<input name="EIN" value="13-1624103"><select name="EINFilterCriteria"><option selected="selected" value="3">Equals</option></select>No charities found'
        with patch.object(c,'identity_fetch',return_value=source.encode()):
            result=c.identity_oh_names('131624103',time.monotonic()+30)
        self.assertTrue(result['complete']);self.assertEqual(result['names'],[])
    def test_oh_contains_search_is_not_accepted_as_exact_ein(self):
        source=(F/'oh-ywca.html').read_text().replace('selected="selected" value="3"','selected="selected" value="1"')
        with patch.object(c,'identity_fetch',return_value=source.encode()):
            with self.assertRaises(ValueError):c.identity_oh_names('131624103',time.monotonic()+30)
    def test_wa_alias_review_still_applies_to_direct_names(self):
        c.IDENTITY_SOURCE_CACHE.clear();raw={'names':[],'complete':True};reviewed={'names':[],'complete':False,'limitation':'Identity conflict'}
        with patch.object(c,'identity_wa_names',return_value=raw),patch.object(c,'identity_wa_alias_review',return_value=reviewed) as review:
            self.assertFalse(c.identity_source_result('WA','123456789',time.monotonic()+30)['complete'])
        review.assert_called_once()

if __name__=='__main__':unittest.main(verbosity=2)
