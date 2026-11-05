"""Search transport punctuation must not alter names or identity decisions."""
import ast, re, subprocess, unittest
from unittest.mock import patch
import registry_snapshot_server as m

CHANGED=('build_search_queries','literal_registry_name_queries','reviewed_queries_first','wi_direct_search_names')

def baseline_functions():
    source=subprocess.check_output(['git','show','HEAD:registry_snapshot_server.py']).decode('utf-8')
    nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name in CHANGED]
    ns=dict(vars(m));exec(compile(ast.Module(body=nodes,type_ignores=[]),'baseline','exec'),ns)
    return {name:ns[name] for name in CHANGED}

def plans(name,ein):
    org=m.checker.Organization(name,ein)
    return [m.build_search_queries(name,ein,max_queries=10),
            m.reviewed_queries_first(name,ein,m.organization_name_variants(name,ein),limit=8),
            m.literal_registry_name_queries(name,ein),m.wi_direct_search_names(org),
            m.nj_name_fallback_queries(org),m.wv_preferred_query_variants(name,ein,limit=m.WV_QUERY_LIMIT)]

class Queries(unittest.TestCase):
    def test_all_affected_plans_preserve_words_and_identity_context(self):
        for name in ['John F. Kennedy Center for the Performing Arts','Example Cultural Center','Medical Research Trust']:
            alias=name+' <Govt>';ein='530245017'
            token=m.REVIEWED_NAME_CONTEXT.set({ein:(alias,)})
            try:
                identities=m.organization_match_target_variants(name,ein)
                for plan in plans(name,ein):
                    self.assertTrue(plan)
                    self.assertFalse(any('<' in q or '>' in q for q in plan),plan)
                    self.assertTrue(any('Govt' in q for q in plan),plan)
                self.assertEqual(m.known_names_for_ein(ein),[alias])
                self.assertEqual(m.organization_match_target_variants(name,ein),identities)
                self.assertTrue(m.reviewed_identity_queries_completed([name,alias.replace('<','').replace('>','')],[name,alias]))
                self.assertFalse(m.reviewed_identity_queries_completed([name],[name,alias]))
            finally:m.REVIEWED_NAME_CONTEXT.reset(token)

    def test_only_delimiters_change_no_words_are_dropped(self):
        for value in ['Sjögren’s Foundation','A.B.C. Inc.','A & B','Alpha-Beta','<Local> Museum','A<B>C']:
            got=m.plain_registry_query(value)
            self.assertEqual(re.findall(r'\w+',got),re.findall(r'\w+',value))
            if not any(c in value for c in '<>'):self.assertEqual(got,value)

    def test_unrelated_records_remain_rejected(self):
        self.assertFalse(m.registry_name_is_safe_for_org('Robert F. Kennedy Center for Justice and Human Rights',
                         'John F. Kennedy Center for the Performing Arts','530245017'))

if __name__=='__main__':unittest.main()
