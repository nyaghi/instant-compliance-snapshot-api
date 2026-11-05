import json,tempfile
from pathlib import Path
from testing.test_gate25_repair import LinkedDC
from deployment import state_snapshots as ss,desktop_source_evidence as desktop

case=LinkedDC();case.setUp()
case.r.update(comments='Previous expired registration',execution_version='local-gate25',evidence_url='')
with tempfile.TemporaryDirectory() as folder:
    update=desktop.persist_completion(case.r,case.p,ss.SQLiteStore(Path(folder)/'snapshot.sqlite'))
base=dict(case.r,desktop_evidence_request=case.q)
base.pop('_worker_desktop_evidence',None)
print(json.dumps(dict(base=base,update=update)))
