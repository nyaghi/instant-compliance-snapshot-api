"""Diagnostics preserve the existing parser output and exception, without I/O."""
import ast,subprocess,types,unittest
from pathlib import Path
from unittest.mock import Mock
from deployment.queue_engine import observe_me_rejected_page,FloridaTrace

class RejectedPage(unittest.TestCase):
 def test_success_returns_same_object_and_records_nothing(self):
  result=[{'name':'Example'}];parse=Mock(return_value=result);m=types.SimpleNamespace(me_parse_search_rows=parse);trace=FloridaTrace()
  with observe_me_rejected_page(m,trace):self.assertIs(m.me_parse_search_rows('original HTML'),result)
  parse.assert_called_once_with('original HTML');self.assertIs(m.me_parse_search_rows,parse);self.assertEqual(trace.events,[])
 def test_same_exception_with_bounded_visible_public_error_and_no_hidden_values(self):
  error=ValueError('unrecognized');parse=Mock(side_effect=error);m=types.SimpleNamespace(me_parse_search_rows=parse);trace=FloridaTrace()
  body='<html><script>private-script</script><style>private-style</style><textarea>private-textarea</textarea><input type="hidden" value="private-hidden"><!--private-comment--><h1>Application Error</h1><p>Unable to process search. token=private-token</p><a href="https://example.com/?private-url">Help</a></html>'
  with observe_me_rejected_page(m,trace):
   with self.assertRaises(ValueError) as caught:m.me_parse_search_rows(body)
  self.assertIs(caught.exception,error);parse.assert_called_once_with(body);self.assertIs(m.me_parse_search_rows,parse)
  text=trace.events[0]['visible_text'];self.assertIn('Application Error',text);self.assertNotIn('private',text);self.assertLessEqual(len(text),1600)
 def test_diagnostic_failure_never_replaces_original_exception(self):
  error=ValueError('source');parse=Mock(side_effect=error);m=types.SimpleNamespace(me_parse_search_rows=parse);trace=Mock();trace.record.side_effect=RuntimeError('sink')
  with observe_me_rejected_page(m,trace):
   with self.assertRaises(ValueError) as caught:m.me_parse_search_rows('<html>error</html>')
  self.assertIs(caught.exception,error)
 def test_entire_engine_other_than_new_observer_is_identical(self):
  root=Path(__file__).resolve().parents[2];old=ast.parse(subprocess.check_output(['git','show','13f47e4:deployment/queue_engine.py'],cwd=root).decode())
  new=ast.parse((root/'deployment/queue_engine.py').read_text());strip_rejected_page_observer(new)
  self.assertEqual(ast.dump(old),ast.dump(new))
 def test_rejected_entry_form_preserves_same_error_and_redacts_hidden_fields(self):
  failure=ValueError('Original form rejected')
  class Session:
   stage='search form GET';form_html='<html><input type="hidden" value="private-hidden"><h1>Public application error</h1></html>'
   def search(self,query):raise failure
  original=Session.search;m=types.SimpleNamespace(me_parse_search_rows=Mock(),MaineRegistrySession=Session);trace=FloridaTrace()
  with observe_me_rejected_page(m,trace):
   with self.assertRaises(ValueError) as caught:Session().search('Original query')
  self.assertIs(caught.exception,failure);self.assertIs(Session.search,original)
  self.assertEqual(trace.events[0]['event'],'me_form_rejected');self.assertNotIn('private',trace.events[0]['visible_text'])

def strip_rejected_page_observer(tree):
 added=[n for n in tree.body if getattr(n,'name','')=='observe_me_rejected_page']
 if not added:return
 assert len(added)==1;tree.body.remove(added[0])
 fn=next(n for n in tree.body if getattr(n,'name','')=='observe_transport');found=0
 for n in ast.walk(fn):
  if isinstance(n,ast.Try):
   for i,x in enumerate(n.body):
    if isinstance(x,ast.If) and ast.unparse(x.test)=="state == 'ME'" and len(x.body)==1 and isinstance(x.body[0],ast.With):
     assert ast.unparse(x.body[0].items[0].context_expr)=='observe_me_rejected_page(master, trace)'
     assert ast.unparse(x.body[0].body[0])=='yield trace'
     assert len(x.orelse)==1 and ast.unparse(x.orelse[0])=='yield trace'
     n.body[i:i+1]=x.orelse;found+=1
 assert found==1

if __name__=='__main__':unittest.main(verbosity=2)
