"""Allow exactly the user-requested private-lab concurrency control."""
import ast
from pathlib import Path
import subprocess


def strip_state_ceiling(tree):
    root = Path(__file__).resolve().parents[2]
    original = subprocess.check_output(['git','show','83ef980:deployment/durable_queue.py'],cwd=root).decode()
    expected = original.replace(
        "'states', 'mode', 'kind'}", "'states', 'mode', 'kind', 'state_concurrency'}")
    old_return = """    return {'organization_name': name.strip(), 'ein': ein.replace('-', ''),
            'alternate_names': aliases, 'states': sorted(set(states)), 'mode': mode, 'kind': kind}"""
    new_return = """    concurrency = payload.get('state_concurrency', 15)
    if type(concurrency) is not int or concurrency not in (5, 10, 15):
        raise ValueError('Lab state concurrency must be 5, 10 or 15')
    if kind == 'discovery' and 'state_concurrency' in payload:
        raise ValueError('State concurrency applies only to registration')
    normalized = {'organization_name': name.strip(), 'ein': ein.replace('-', ''),
                  'alternate_names': aliases, 'states': sorted(set(states)), 'mode': mode, 'kind': kind}
    if concurrency != 15:
        normalized['state_concurrency'] = concurrency
    return normalized"""
    assert old_return in expected
    expected = expected.replace(old_return, new_return)
    assert expected.count("running[w['id']] >= 15") == 2
    expected = expected.replace("running[w['id']] >= 15", "running[w['id']] >= w['payload'].get('state_concurrency', 15)")
    expected = expected.replace('slot_limit=ceiling, admission=admission_evidence,',
        "slot_limit=ceiling, admission=admission_evidence,\n                                   state_concurrency=w['payload'].get('state_concurrency', 15),")
    assert ast.dump(tree) == ast.dump(ast.parse(expected)), 'Change beyond the exact lab state-ceiling control'
    tree.body = ast.parse(original).body
