"""Failure-only sanitized transport facts; no request/retry/deadline changes."""
import traceback
import urllib.error


def failure(exc,elapsed,remaining,attempt):
    chain=[];seen=set();current=exc
    while isinstance(current,BaseException) and id(current) not in seen and len(chain)<5:
        seen.add(id(current))
        frames=[f.name for f in traceback.extract_tb(current.__traceback__)][-12:]
        chain.append({'type':type(current).__name__,'frames':frames})
        reason=getattr(current,'reason',None)
        current=current.__cause__ or current.__context__ or (reason if isinstance(reason,BaseException) else None)
    functions={name for item in chain for name in item['frames']}
    phase=('dns' if 'getaddrinfo' in functions else 'tls' if 'do_handshake' in functions else
           'response_headers' if '_read_status' in functions else
           'response_read' if functions & {'_safe_read','_read_chunked','readinto'} else
           'connect' if 'connect' in functions else 'unresolved')
    return {'source':'DC_LICENSE_API','attempt':attempt,'elapsed_seconds':round(elapsed,3),
        'remaining_seconds':round(max(0,remaining),3),'observed_phase':phase,'exceptions':chain}
