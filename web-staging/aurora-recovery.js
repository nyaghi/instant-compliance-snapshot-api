/* Permanent staging only. Completed rows are stored apart from the connector. */
(() => {
  "use strict";
  const RETAIN_MS = 20 * 60_000;
  const BROWSER_STATES = new Set(["AL","GA","IL","MS","NC","NM","NV","NY","TN"]);
  const digits = value => String(value || "").replace(/\D/g, "");
  let database;
  function openStore() {
    if (!database) database = new Promise((resolve, reject) => {
      const open = indexedDB.open("cc-aurora-recovery", 1);
      open.onupgradeneeded = () => {
        const store = open.result.createObjectStore("runs", {keyPath:"id"});
        store.createIndex("owner", "owner");
      };
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
      open.onblocked = () => reject(new Error("Recovery storage is unavailable."));
    }).catch(error => { database = null; throw error; });
    return database;
  }
  async function transact(mode, work) {
    const db = await openStore();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction("runs", mode);
      const request = work(transaction.objectStore("runs"));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onabort = () => reject(transaction.error || new Error("Recovery storage was interrupted."));
      transaction.onerror = () => reject(transaction.error || new Error("Recovery storage failed."));
    });
  }
  const ownerKey = (email, device) => JSON.stringify([email.trim().toLowerCase(), device]);
  const read = id => transact("readonly", store => store.get(id));
  const write = run => transact("readwrite", store => store.put(run));
  const discard = id => transact("readwrite", store => store.delete(id));
  async function list(email, device) {
    const owner = ownerKey(email, device);
    const saved = await transact("readonly", store => store.index("owner").getAll(owner));
    const cutoff = Date.now() - RETAIN_MS;
    await Promise.allSettled(saved.filter(run => run.updated < cutoff).map(run => discard(run.id)));
    return saved.filter(run => run.updated >= cutoff).sort((a,b) => b.updated-a.updated);
  }
  function make({name,ein,email,device,states,aliases}) {
    return {id:crypto.randomUUID(),owner:ownerKey(email,device),name,ein,states:[...states],aliases:[...aliases],
      rows:{},phase:"running",updated:Date.now()};
  }
  function pending(run) {
    return run.states.filter(state => !Object.hasOwn(run.rows,state));
  }
  function rowFor(run, row) {
    return row && run.states.includes(row.state) && digits(row.ein) === digits(run.ein);
  }
  function keepRow(row) {
    const {workflow_observation, archive_observation, lab_diagnostic, evidence_metrics, ...data} = row;
    return structuredClone(data);
  }

  function journal(run) {
    let queued = false, flush = Promise.resolve(), saved = 0;
    const persist = () => {
      queued = true;
      flush = flush.catch(() => {}).then(async () => {
        if (!queued) return;
        queued = false;
        const snapshot = structuredClone(run);
        await write(snapshot);
        saved = Object.keys(snapshot.rows).length;
      });
      flush.catch(() => {});
      return flush;
    };
    async function finish(phase, rows = []) {
      for (const row of rows) if (rowFor(run,row)) run.rows[row.state] = keepRow(row);
      run.phase = phase;
      run.updated = Date.now();
      await persist();
      return saved;
    }
    function record(row) {
      if (!rowFor(run,row)) return;
      run.rows[row.state] = keepRow(row);
      run.updated = Date.now();
      void persist();
    }
    return {record,finish,begin:persist};
  }

  function monitor(states, probe, alert) {
    const outstanding = new Set(states.filter(state => BROWSER_STATES.has(state)));
    let lastActivity = performance.now(), slowReplies = 0, checking = false, stopped = false;
    const timer = setInterval(async () => {
      if (stopped || checking || outstanding.size < 2 || performance.now()-lastActivity < 30_000) return;
      checking = true;
      const start = performance.now(), activity = lastActivity;
      try {
        const reply = await probe().catch(() => null);
        if (stopped || activity !== lastActivity || outstanding.size < 2) return;
        slowReplies = !reply?.ok || performance.now()-start > 2_000 ? slowReplies+1 : 0;
        if (slowReplies === 2) alert();
      } finally { checking = false; }
    }, 5_000);
    return {
      completed(state) {
        if (outstanding.delete(state)) {
          lastActivity = performance.now();
          slowReplies = 0;
        }
      },
      stop() { stopped = true; clearInterval(timer); }
    };
  }

  function exclusive(owner, ein, start) {
    if (!navigator.locks) return start();
    return navigator.locks.request("cc-aurora-check:"+owner+":"+digits(ein), {ifAvailable:true}, async lock => {
      if (!lock) throw new Error("A check for this organization is already open in another tab.");
      return start();
    });
  }
  async function resume(id, email, device, start) {
    if (!navigator.locks) throw new Error("This browser cannot safely resume a saved check.");
    const owner = ownerKey(email, device);
    const entry = await read(id);
    if (!entry || entry.owner !== owner) throw new Error("This check is no longer ready to resume.");
    return exclusive(owner, entry.ein, async () => {
      const run = await read(id);
      if (!run || run.owner!==owner || run.updated<Date.now()-RETAIN_MS
          || run.phase!=="paused" || !pending(run).length)
        throw new Error("This check is no longer ready to resume.");
      return start(run);
    });
  }

  function bounded(operation) {
    let timer;
    return Promise.race([operation,new Promise((resolve,reject)=>{
      timer=setTimeout(()=>reject(new Error("Could not confirm that the browser saved the results.")),5000);
    })]).finally(()=>clearTimeout(timer));
  }

  function mount(panel, controls) {
    let generation = 0;
    function show(text, action, callback) {
      panel.replaceChildren(document.createTextNode(text));
      panel.hidden = false;
      if (!action) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ml-2 underline font-semibold";
      button.textContent = action;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try { await callback(); }
        catch (error) { controls.error(error.message || "The saved check could not be opened."); }
        finally { button.disabled = false; }
      });
      panel.append(" ", button);
    }
    function hide() { ++generation; panel.hidden = true; }
    async function refresh() {
      const target = ++generation, account = controls.account();
      if (!account) { panel.hidden = true; return; }
      try {
        const saved = await list(account.email,account.device);
        const current = controls.account();
        if (target !== generation || !current || ownerKey(current.email,current.device)!==ownerKey(account.email,account.device)) return;
        const actionsFor = action => {
          const active = controls.account();
          if (!active || ownerKey(active.email,active.device)!==ownerKey(account.email,account.device))
            throw new Error("Unlock Aurora with the account that started this check.");
          return action();
        };
        const run = saved.find(row => row.phase==="paused" && pending(row).length);
        if (run) {
          const count = pending(run).length;
          show(count+" remaining for "+run.name+".", "Resume remaining states",
            () => actionsFor(() => resume(run.id,account.email,account.device,controls.resume)));
          return;
        }
        const partial = saved.find(row => ["running","interrupted"].includes(row.phase) && Object.keys(row.rows).length);
        if (partial) {
          show("Aurora saved completed states for "+partial.name+".", "View saved results",
            () => actionsFor(() => controls.view(partial.states.map(state => partial.rows[state]).filter(Boolean))));
          return;
        }
        panel.hidden = true;
      } catch { if (target === generation) panel.hidden = true; }
    }
    return {show,hide,refresh};
  }

  window.CCAuroraRecovery = Object.freeze({list,make,pending,journal,discard,monitor,resume,mount,exclusive,bounded});
})();
