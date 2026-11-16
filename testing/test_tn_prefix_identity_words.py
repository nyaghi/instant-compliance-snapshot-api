"""TN historical retrieval must not turn punctuation into identity evidence."""
import json
import re
import unittest
from unittest.mock import patch
from pathlib import Path
from deployment.gates2930_repairs import tn_historical_prefix


class PrefixIdentityWords(unittest.TestCase):
    def test_real_shortlist_rejects_other_hospitals_keeps_exact_and_ein(self):
        import registry_snapshot_server as c
        name="CHILDREN'S HOSPITAL CORPORATION"; ein='042774441'
        with patch.object(c,'known_names_for_ein',side_effect=lambda e:[name,"Boston Children's Hospital"] if e==ein else []):
            for other in ["Children's Hospital of Los Angeles", "Children's Hospital of Michigan", "Children's Hospital at Vanderbilt"]:
                self.assertTrue(all(s['decision']=='rejected' for s in c.final_four_search_candidate_scores(name,ein,'TN',{'name':other})),other)
            self.assertTrue(any(s['decision']=='accepted' for s in c.final_four_search_candidate_scores(name,ein,'TN',{'name':name})))
            self.assertTrue(any(s['decision']=='accepted' for s in c.final_four_search_candidate_scores(name,ein,'TN',{'name':'Other Legal Name','ein':ein})))
            self.assertTrue(all(s['decision']=='rejected' for s in c.final_four_search_candidate_scores(name,ein,'TN',{'name':name,'ein':'123456789'})))

    def test_observed_unrelated_hospitals_are_not_historical_prefixes(self):
        for primary in ["Children's Hospital Corporation", "Children’s Hospital", "The Children's Hospital"]:
            for candidate in ["Children's Hospital of Los Angeles", "Children's Hospital of Michigan", "Children's Hospital at Vanderbilt"]:
                with self.subTest(primary=primary,candidate=candidate):
                    self.assertFalse(tn_historical_prefix([primary],candidate))

    def test_existing_historical_names_remain_eligible_for_review(self):
        for primary,candidate in [
            ('Foster Parents Plan, Inc.',"Foster Parents' Plan for Spanish Children, Inc."),
            ('California Lutheran University','California Lutheran University Foundation'),
            ("Saint Mary's Community Center","Saint Mary’s Community Center Foundation"),
            ('The Foster Parents Plan',"The Foster Parents' Plan for Spanish Children"),
        ]:
            self.assertTrue(tn_historical_prefix([primary],candidate),(primary,candidate))

    def test_seventy_roster_names_do_not_gain_broad_historical_matches(self):
        rows=json.loads((Path(__file__).parent/'fixtures/fresh-five/LOCAL-70.json').read_text())
        self.assertEqual(len(rows),70)
        def old(target,candidate):
            def words(s):
                s=re.sub(r'\b(?:incorporated|inc|corporation|corp|limited|ltd)\.?\s*$','',s.strip(),flags=re.I)
                return re.findall(r'[a-z0-9]+',s.casefold())
            a,b=words(target),words(candidate)
            return len(a)>=3 and len(b)>len(a) and b[:len(a)]==a
        for row in rows:
            name=row['name']
            for candidate in [name, name+' Foundation', 'Unrelated Organization Foundation']:
                with self.subTest(name=name,candidate=candidate):
                    result=tn_historical_prefix([name],candidate)
                    # Unmodified complete names cannot acquire a new match.
                    self.assertFalse(result and not old(name,candidate))
                    if not re.search(r"['’]|^the\s",name,re.I):
                        self.assertEqual(result,old(name,candidate))

    def test_seventy_actual_shortlists_preserve_identity_guards(self):
        import registry_snapshot_server as c
        rows=json.loads((Path(__file__).parent/'fixtures/fresh-five/LOCAL-70.json').read_text())
        for row in rows:
            name,ein=row['name'],row['ein']
            with self.subTest(name=name),patch.object(c,'known_names_for_ein',side_effect=lambda e:row.get('aliases',[]) if e==ein else []):
                exact=c.final_four_search_candidate_scores(name,ein,'TN',{'name':name,'ein':ein})
                conflict=c.final_four_search_candidate_scores(name,ein,'TN',{'name':name,'ein':'999999999'})
                self.assertTrue(any(v['decision']=='accepted' for v in exact))
                self.assertTrue(all(v['decision']=='rejected' for v in conflict))

if __name__=='__main__':unittest.main()
