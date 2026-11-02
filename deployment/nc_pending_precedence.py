"""User policy: identity-confirmed NC In-Process records take precedence."""
import re


def confirmed_pending(row):
    return bool(isinstance(row, dict)
        and row.get('_identity_outcome') == 'accepted'
        and row.get('status') == 'Pending'
        and row.get('raw_status') == 'In-Process'
        and not row.get('unsupported_registration_scope')
        and not row.get('non_charity_scope')
        and (row.get('_nc_application_profile_confirmed') is True
             or re.fullmatch(r'(?:SL|EX)\d+', str(row.get('identifier', '')))))
