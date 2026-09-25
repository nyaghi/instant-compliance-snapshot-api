"""Private lab forkserver template. Imports code once; never executes a lookup.

No organization inputs, completed results, database connections, browser sessions
or task threads enter this process. Each job receives a separate copy-on-write
child; that child and its browser descendants are killed before releasing slots.
"""
import os
from pathlib import Path
import sys
import threading
import time

from deployment.performance_lab import validate_environment, install_http_egress_guard

validate_environment(os.environ)
if not sys.platform.startswith('linux'):
    raise RuntimeError('The warm engine template requires Linux forkserver isolation')
for key in ('CE_LAB_DATABASE_URL','CE_TEST_DATABASE_URL','RENDER_API_KEY'):
    os.environ.pop(key,None)
os.environ['CE_LAB_DURABLE_QUEUE']='0'
install_http_egress_guard()
started, cpu_started = time.monotonic(), time.process_time()
import registry_snapshot_server as master
IMPORT_SECONDS=time.monotonic()-started
IMPORT_CPU_SECONDS=time.process_time()-cpu_started
PRELOAD_PID=os.getpid()
if threading.active_count()!=1 or len(list(Path('/proc/self/task').iterdir()))!=1:
    raise RuntimeError('Refusing to fork a template with active library threads')
