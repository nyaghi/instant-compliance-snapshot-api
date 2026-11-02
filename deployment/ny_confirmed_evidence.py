"""Preserve the exact NY detail name after the existing identity matcher accepts it."""
import re

def preserves_confirmed_detail(result):
    from deployment.lab_identity import trial_identity
    if not trial_identity() or getattr(result, 'state', '') != 'NY':
        return False
    proof = getattr(result, '_ny_confirmed_detail', None)
    if (not isinstance(proof, dict) or getattr(result, 'success', False) is not True
            or getattr(result, '_cc_identity_review', None)
            or getattr(result, 'status', '') not in {'Current', 'Upcoming Filing', 'Exempt', 'Delinquent'}):
        return False
    identifier = proof.get('org_id', '')
    ein = re.sub(r'\D', '', str(getattr(result, 'ein', '')))
    return bool(re.fullmatch(r'\d{2}-\d{2}-\d{2}', identifier)
        and len(ein) == 9 and proof.get('ein') == ein
        and proof.get('name') and proof['name'] == getattr(result, 'matched_registry_name', '')
        and getattr(result, 'matched_registry_identifier', '') == ein
        and getattr(result, 'source_url', '') == 'https://charities-search.ag.ny.gov/RegistrySearch/' + identifier)
