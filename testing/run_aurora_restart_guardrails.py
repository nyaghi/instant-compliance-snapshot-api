"""Restart an isolated Chrome profile and resume the original ten recorded scopes.

The browser sees only a test page with no outbound registry traffic.
"""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(os.environ["LOCALAPPDATA"]) / "CharityClarityQA"
ORIGINAL = ROOT / "fl-source-repair-20261127" / "live-original10"
OUTPUT = ROOT / "aurora-recovery-20261127"
ORIGIN = "https://recovery-test.example.com/"
OWNER = {"email": "test@example.com", "device": "recovery-test-browser"}
SCRIPT = (Path(__file__).resolve().parents[1] / "web-staging" / "aurora-recovery.js").read_text(encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def start_page(chromium, directory):
    context = chromium.launch_persistent_context(directory, headless=True)
    page = context.pages[0]
    page.route("**/*", lambda route: route.fulfill(
        status=200, content_type="text/html", body="<title>Aurora recovery test</title><script>"+SCRIPT+"</script>"
    ) if route.request.url == ORIGIN else route.abort())
    page.goto(ORIGIN)
    return context, page


def main():
    scopes = []
    for entry in read(ORIGINAL / "PROGRESS.json"):
        tag = entry["tag"]
        baseline = read(ORIGINAL / (tag+"-SCOPE.json"))
        result = read(ORIGINAL / (tag+"-RESULT.json"))
        rows = [{"state": item["cells"][2], "ein":baseline["e"], "status":item["cells"][3],
                 "evidence_url": item["links"][0][1]} for item in result["rows"]]
        assert len(rows) == 38 and len({row["state"] for row in rows}) == 38
        scopes.append({"tag":tag, "name":baseline["o"], "ein":baseline["e"], "aliases":baseline["a"],
                       "states":baseline["s"], "rows":rows})
    with TemporaryDirectory(prefix="cc-recovery-local-test-") as folder, sync_playwright() as browser:
        context, page = start_page(browser.chromium, folder)
        ids = page.evaluate("""async ({scopes,owner}) => {
          const out=[];
          for(const scope of scopes) {
            const {rows,...input}=scope;
            const run=CCAuroraRecovery.make({...owner,...input});
            const journal=CCAuroraRecovery.journal(run);
            for(const row of rows.slice(0,18))journal.record(row);
            await journal.finish("paused");
            out.push(run.id);
          }
          return out;
        }""", {"scopes":scopes,"owner":OWNER})
        context.close()
        context, page = start_page(browser.chromium, folder)
        checked = page.evaluate("""async ({scopes,owner,ids}) => {
          const api=CCAuroraRecovery, out=[];
          const other=await api.list("other@example.com",owner.device);
          if(other.length)throw Error("Cross-account recovery");
          const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
          for(let i=0;i<ids.length;i++){
            const scope=scopes[i], id=ids[i];
            let executions=0, release;
            const latch=new Promise(resolve=>{release=resolve;});
            let entered;
            const contended=new Promise(resolve=>{entered=resolve;});
            const primary=api.resume(id,owner.email,owner.device,async run=>{
              executions++;
              entered();
              await latch;
              const completed=Object.values(run.rows), remaining=api.pending(run);
              if(!same(run.aliases,scope.aliases) || !same(run.states,scope.states) || completed.length!==18 || remaining.length!==20)
                throw Error("Original scope or row count changed");
              for(const row of completed)if(!same(row,scope.rows.find(x=>x.state===row.state)))
                throw Error("Saved evidence or status changed");
              if(remaining.some(state=>Object.hasOwn(run.rows,state)))throw Error("Repeated state");
              const journal=api.journal(run);
              await journal.finish("running");
              await journal.finish("completed",scope.rows.filter(row=>remaining.includes(row.state)));
              out.push({tag:scope.tag,completed:completed.length,resumed:remaining.length,retained:Object.keys(run.rows).length});
            });
            await contended;
            const secondary=await api.resume(id,owner.email,owner.device,async()=>{executions++;}).then(()=>false,()=>true);
            release();
            await primary;
            if(!secondary || executions!==1)throw Error("Duplicate resume");
          }
          return out;
        }""", {"scopes":scopes,"ids":ids,"owner":OWNER})
        context.close()
    report={"cases":checked,"saved_status_evidence_rows":sum(row["completed"] for row in checked),
            "remaining_states_only":sum(row["resumed"] for row in checked),"browser_restart":True,
            "live_registry_requests":0,"cross_account_access":False,"duplicate_resume":False}
    (OUTPUT/"RESTART-ORIGINAL10-REPLAY.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
