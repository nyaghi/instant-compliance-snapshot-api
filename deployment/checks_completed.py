"""Staging usage ledger; independent of registry execution and status rules."""
import json, re, time

# Frozen audit cutoff, not a fabricated count. Older focused/state-only tests
# and workflows with outstanding browser reservations are deliberately omitted.
HISTORY_CUTOFF = 1793910019.549095

def initialize(pool):
    with pool.connection() as db, db.transaction():
        db.execute("SET LOCAL statement_timeout='5000ms'")
        db.execute('CREATE TABLE IF NOT EXISTS cc_completed_checks '
                   '(id text PRIMARY KEY, completed double precision NOT NULL, origin text NOT NULL)')
        db.execute("INSERT INTO cc_completed_checks(id,completed,origin) "
                   "SELECT 'historical:'||id,finished,'historical-broad-workflow' FROM cc_lab_workflows "
                   "WHERE kind='registration' AND phase='completed' AND submitted<=%s "
                   "AND jsonb_array_length(payload->'states')>=27 "
                   "AND payload->>'external_state_slots'='0' ON CONFLICT DO NOTHING", (HISTORY_CUTOFF,))

def completed_id(payload, states):
    ident=payload.get('check_id')
    chosen=payload.get('states')
    if (not isinstance(ident,str) or not re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}',ident)
            or not isinstance(chosen,list) or not 1<=len(chosen)<=len(states) or len(set(chosen))!=len(chosen)
            or any(s not in states for s in chosen)
            or not re.fullmatch(r'\d{2}-?\d{7}',str(payload.get('ein','')))
            or payload.get('run_completed') is not True):
        raise ValueError('Completed organization run required')
    return 'run:'+ident

def handle(master,handler,queue):
    try:
        n=int(handler.headers.get('Content-Length','0'))
        if not 0<n<=8192: raise ValueError('Invalid request size')
        p=json.loads(handler.rfile.read(n))
        if not isinstance(p,dict): raise ValueError('Object required')
        email=master.normalize_email(p.get('email','')); passcode=str(p.get('admin_passcode','')).strip()
        if master.staging_access_error(email,passcode) or not master.is_verified_internal_passcode(email,passcode):
            return handler._send_json(403,{'error':'Authorized staging access required'})
        action=p.get('action')
        ident=completed_id(p,master.SUPPORTED_STATES) if action=='complete' else None
        if action not in {'read','complete'}: raise ValueError('Invalid action')
        with queue.pool.connection(timeout=2) as db, db.transaction():
            db.execute("SET LOCAL statement_timeout='1500ms'")
            if ident:
                db.execute('INSERT INTO cc_completed_checks(id,completed,origin) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                           (ident,time.time(),'completed-ui-run'))
            count=db.execute('SELECT count(*) AS count FROM cc_completed_checks').fetchone()['count']
        return handler._send_json(200,{'count':count,'label':'Organization checks completed'}, {'Cache-Control':'no-store'})
    except (ValueError,TypeError,KeyError,UnicodeError):
        return handler._send_json(400,{'error':'Invalid completed-check request'})
    except Exception:
        return handler._send_json(503,{'error':'Usage count temporarily unavailable'})
