import ast,json,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace as NS
import registry_snapshot_server as m
class WashingtonComment(unittest.TestCase):
 def test_actual_live_reason_survives_public_comment(self):
  row=json.loads((Path(__file__).parent/'fixtures/gates29-30/WA-LIVE-REVIEW-COMMENT.json').read_text(encoding='utf-8'))
  text=m.comments_for_result_base(NS(**row),'','Unable to Confirm')
  self.assertIn('entered 872410117; registry 872610117',text);self.assertIn('accept or reject',text);self.assertNotIn('reports Unable',text)
 def test_other_comment_branches_ast_unchanged(self):
  old=ast.parse(subprocess.check_output(['git','show','49dc980ee8d813f195be8908c8ac30f0458bad88:registry_snapshot_server.py'],cwd=Path(m.__file__).parent).decode('utf-8'))
  new=ast.parse(Path(m.__file__).read_text(encoding='utf-8'));a=next(x for x in old.body if getattr(x,'name','')=='comments_for_result_base');b=next(x for x in new.body if getattr(x,'name','')=='comments_for_result_base');b.body.pop(0);self.assertEqual(ast.dump(a),ast.dump(b))
