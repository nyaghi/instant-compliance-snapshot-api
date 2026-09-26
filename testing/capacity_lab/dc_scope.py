"""Remove only the separately tested DC recovery branch from historical AST guards."""
import ast


def remove_dc_recovery(tree):
    for name in ('dc_repeated_name_prefix', 'dc_repeated_name_identity'):
        tree.body.remove(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name))
    identity = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'licensed_charity_identity')
    branch = next(n for n in identity.body if isinstance(n, ast.If)
                  and ast.unparse(n.test) == "decision['decision'] == 'rejected'")
    expected = ast.parse('if state == "DC" and decision["reason"] != "REJECT_DIFFERENT_EIN":\n return dc_repeated_name_identity(org, row, deadline)').body[0]
    assert ast.dump(branch.body[0]) == ast.dump(expected), 'DC exception scope changed'
    branch.body.pop(0)
