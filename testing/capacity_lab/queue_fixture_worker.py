"""Only for OS-process recovery tests; never used by deployed workers."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from deployment.durable_queue import Queue
from deployment.queue_worker import Supervisor

q=Queue(os.environ['CE_TEST_DATABASE_URL'],test_schema=os.environ['CC_TEST_SCHEMA'])
s=Supervisor(q,'fixture-performance-lab',1,
             [sys.executable,str(ROOT/'testing/capacity_lab/queue_fixture_task.py')])
Path(sys.argv[1]).write_text(s.id)
s.run()
