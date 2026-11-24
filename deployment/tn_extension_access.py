"""Remember a verified pilot browser for Tennessee extension checks only."""
import hashlib
import re
import secrets
from http.cookies import CookieError, SimpleCookie

COOKIE = '__Host-cc_tn_extensions'
REMEMBER_SECONDS = 90 * 86400
ACTIVE_SECONDS = 3600
SCHEMA = '''
CREATE TABLE IF NOT EXISTS cc_tn_extension_browsers (
    secret text PRIMARY KEY, account text NOT NULL REFERENCES cc_alert_accounts(account) ON DELETE CASCADE,
    expires double precision NOT NULL, active_until double precision NOT NULL
);
'''

def browser_key(handler):
    try:
        token = SimpleCookie(handler.headers.get('Cookie', ''))[COOKIE].value
    except (KeyError, ValueError, CookieError):
        return None
    if re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return hashlib.sha256(token.encode('ascii')).hexdigest()
    return None


def account(alerts, conn, handler, now, *, email=None, unlock=False, response_headers=None):
    signed_in = alerts.account(conn, handler)
    if signed_in and email and signed_in != email:
        return None
    key = browser_key(handler)
    if signed_in and not unlock:
        return signed_in
    if not signed_in and not key:
        return None
    if signed_in and unlock:
        conn.execute('SELECT pg_advisory_xact_lock(824527339)')
        conn.execute(SCHEMA)
    record = conn.execute(
        'SELECT account,active_until FROM cc_tn_extension_browsers WHERE secret=%s AND expires>%s',
        (key, now)).fetchone() if key else None
    if not unlock:
        if record and record['active_until'] > now and (not email or email == record['account']):
            return record['account']
        return None
    # The shared staging passcode alone cannot identify the owner. Bootstrapping
    # requires a verified account; resuming requires its private browser token.
    if not email or not signed_in and (not record or record['account'] != email):
        return None
    conn.execute('DELETE FROM cc_tn_extension_browsers WHERE expires<=%s', (now,))
    if record and record['account'] == email:
        updated=conn.execute(
            'UPDATE cc_tn_extension_browsers SET active_until=%s WHERE secret=%s AND account=%s AND expires>%s RETURNING account',
            (now + ACTIVE_SECONDS, key, email, now)).fetchone()
        if not updated:
            return None
    else:
        if key:
            conn.execute('DELETE FROM cc_tn_extension_browsers WHERE secret=%s', (key,))
        token = secrets.token_urlsafe(32)
        key = hashlib.sha256(token.encode('ascii')).hexdigest()
        conn.execute('INSERT INTO cc_tn_extension_browsers(secret,account,expires,active_until) VALUES (%s,%s,%s,%s)',
                     (key,email,now+REMEMBER_SECONDS,now+ACTIVE_SECONDS))
        response_headers['Set-Cookie'] = f'{COOKIE}={token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age={REMEMBER_SECONDS}'
    return email
