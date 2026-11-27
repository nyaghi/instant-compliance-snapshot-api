"""Staging browser sign-in with the existing private staging key.

The session only authorizes browser reads. Workflow and admin APIs retain their
existing Authorization checks.
"""
import hmac
from http.cookies import CookieError, SimpleCookie
import re
import secrets
import time
from urllib.parse import parse_qs

PATH = '/staging-sign-in'
COOKIE = '__Host-cc-staging-browser'
SESSION_SECONDS = 3600
TOKEN = re.compile(r'(\d{10})\.([a-f0-9]{32})\.([a-f0-9]{64})')


def signature(key, value):
    return hmac.digest(key.encode(), b'cc-staging-browser-v1\0' + value.encode(), 'sha256').hex()


def valid_session(header, key, now=None):
    if len(header) > 8192 or COOKIE not in header:
        return False
    try:
        cookie = SimpleCookie(header).get(COOKIE)
    except CookieError:
        return False
    found = TOKEN.fullmatch(cookie.value) if cookie else None
    if not found:
        return False
    expires, nonce, supplied = found.groups()
    now = time.time() if now is None else now
    return now < int(expires) <= now + SESSION_SECONDS and hmac.compare_digest(
        supplied, signature(key, expires + '.' + nonce))


def new_session(key, now=None):
    now = time.time() if now is None else now
    value = f'{int(now) + SESSION_SECONDS}.{secrets.token_hex(16)}'
    return f'{COOKIE}={value}.{signature(key, value)}; Path=/; Secure; HttpOnly; SameSite=Strict'


def form(handler, status=200, include_body=True):
    message = '<p role="alert">The staging passcode was rejected.</p>' if status == 403 else ''
    body = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CharityClarity staging sign-in</title>
<style>body{{font:1rem system-ui;color:#102b55;max-width:34rem;margin:4rem auto;padding:0 1.25rem}}label,input,button{{display:block;margin:0.8rem 0}}input,button{{font:inherit;padding:.55rem}}input{{width:min(95%,26rem)}}button{{background:#102b55;color:white;border:0;border-radius:.3rem}}:focus-visible{{outline:3px solid #43659a;outline-offset:3px}}</style>
<main><h1>CharityClarity staging</h1>
<p>Enter your staging passcode to open Aurora.</p>{message}
<form method="post" action="{PATH}" autocomplete="off">
<label for="passcode">Staging passcode</label>
<input id="passcode" name="passcode" type="password" minlength="40" maxlength="512" autocomplete="off" required>
<button type="submit">Open Aurora</button></form></main></html>'''.encode()
    handler.send_response(status)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Referrer-Policy', 'no-referrer')
    handler.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
    handler.end_headers()
    if include_body:
        handler.wfile.write(body)


def sign_in(handler, key, origin):
    # A same-origin HTML form is the only session-issuing operation.
    try:
        length = int(handler.headers.get('Content-Length', 0))
        if (handler.headers.get('Origin') != origin or handler.headers.get('Transfer-Encoding')
                or handler.headers.get_content_type() != 'application/x-www-form-urlencoded'
                or not 1 <= length <= 2048):
            raise ValueError('Invalid sign-in request')
        timeout = handler.connection.gettimeout()
        handler.connection.settimeout(4)
        try:
            inputs = parse_qs(handler.rfile.read(length).decode('utf-8'),
                              strict_parsing=True, max_num_fields=1, errors='strict')
        finally:
            handler.connection.settimeout(timeout)
        if set(inputs) != {'passcode'} or len(inputs['passcode']) != 1:
            raise ValueError('Invalid sign-in request')
        if not hmac.compare_digest(inputs['passcode'][0].encode(), key.encode()):
            raise ValueError('Invalid sign-in request')
    except (ValueError, OSError):
        handler.close_connection = True
        return form(handler, 403)
    handler.send_response(303)
    handler.send_header('Location', '/?collector_layout=duo')
    handler.send_header('Set-Cookie', new_session(key))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('Content-Length', '0')
    handler.end_headers()
