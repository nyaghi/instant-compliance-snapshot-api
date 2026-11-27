"""Permanent staging Aurora pause and resume integration."""


def bind(text):
    text = text.replace("\r\n", "\n")
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise RuntimeError("Aurora recovery marker changed: " + old[:70])
        text = text.replace(old, new)

    replace("</head>", '<script src="/aurora-recovery.js?v=1"></script></head>')
    replace('<div id="progressBox"', '''<div id="auroraRecoveryStatus" hidden role="status"
                class="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-800"></div>
              <div id="progressBox"''')
    replace('async function runStateChecks(states, einValue, emailValue, organizationNameValue, signal)',
            'async function runStateChecks(states, einValue, emailValue, organizationNameValue, signal, recovery = null)')
    replace("states,aliases:runAlternateNames,mode:'standard',signal,userStop:!!signal,",
            "states,aliases:recovery?.aliases ?? runAlternateNames,mode:'standard',signal,userStop:!!signal,recovery,")

    replace('    downloadExcelButton.addEventListener("click", downloadExcel);', r'''
    const recoveryAPI = window.CCAuroraRecovery;
    let recoveryPanel, activeRecovery = null;
    const recoveryAccount = () => internalUnlocked && !runController && !connectorPreflightPending
      ? {email:email.value.trim(),device:getDeviceId()} : null;
    function setupRecovery(run, states) {
      if (!run || !recoveryPanel) return null;
      const saved = recoveryAPI.journal(run);
      const pause = new AbortController();
      const monitor = recoveryAPI.monitor(states,
        () => window.CCNYConnector.probe(),
        () => recoveryPanel.show("Chrome is taking longer than expected. You can wait or pause browser checks.",
          "Pause browser checks", () => {
            pause.abort(new DOMException("Browser checks paused","AbortError"));
            recoveryPanel.show("Pausing browser checks. Server checks are finishing.");
          }));
      return {run, saved, monitor, signal:pause.signal, aliases:run.aliases,
        record(row) { monitor.completed(row.state); saved.record(row); }};
    }

    function orderedRecoveryRows(run, rows) {
      const merged = {...run.rows};
      for(const row of rows) if(run.states.includes(row.state) &&
          String(row.ein||"").replace(/\D/g,"")===String(run.ein).replace(/\D/g,""))
        merged[row.state]=row;
      return run.states.map(state=>merged[state]).filter(Boolean);
    }

    async function finishRecovery(recovery, rows, safe) {
      if (!recovery) return {rows,ready:false};
      const ordered = orderedRecoveryRows(recovery.run, rows);
      try {
        await recoveryAPI.bounded(recovery.saved.finish(safe ? "paused" : "interrupted", ordered));
        return {rows:ordered,ready:safe && recoveryAPI.pending(recovery.run).length>0};
      } catch {
        return {rows:ordered,ready:false};
      }
    }

    async function resumeSavedRecovery(run) {
      const account = recoveryAccount();
      if (!account) throw new Error("Unlock Aurora to resume this check.");
      const remaining = recoveryAPI.pending(run);
      connectorPreflightPending = true;
      submitButton.disabled = true;
      let ownsConnector = false;
      try {
        const readiness = await window.CCNYConnector.preflight(
          remaining.filter(state=>["NY","IL","GA","AL","NC","NV","TN","NM","MS"].includes(state)));
        if(!readiness?.ok) throw new Error("The registry browser connector is unavailable. The saved results are available.");
        ownsConnector = true;
        if(email.value.trim()!==account.email || getDeviceId()!==account.device || !internalUnlocked)
          throw new Error("The signed-in account changed. Unlock Aurora again.");
        await recoveryAPI.bounded(recoveryAPI.journal(run).finish("running"));
        organizationName.value = run.name;
        ein.value = run.ein;
        organizationName.dispatchEvent(new Event("input", {bubbles:true}));
        ein.dispatchEvent(new Event("input", {bubbles:true}));
        stateCheckboxes.forEach(box => { box.checked = run.states.includes(box.value); });
        window.CCIdentity.setBusy(true);
        runController = new AbortController();
        activeRecovery = setupRecovery(run, remaining);
        recoveryPanel.hide();
        progressBox.classList.remove("hidden");
        progressCount.textContent = "0 of " + remaining.length;
        document.getElementById("progressLabel").textContent = "Checking remaining states…";
        stopRun.hidden = false;
        stopRun.disabled = false;
        stopRun.textContent = "Stop run";
        startElapsedTimer();
        const result = await runStateChecks(remaining,run.ein,account.email,run.name,runController.signal,activeRecovery);
        stopElapsedTimer();
        if(result.paused) {
          const saved = await finishRecovery(activeRecovery,result.partialResults,result.cleanupConfirmed);
          if(saved.rows.length)renderResults(saved.rows);
          return;
        }
        renderResults(orderedRecoveryRows(run,result));
        await activeRecovery.saved.finish("completed",result);
        void recoveryAPI.discard(run.id).catch(()=>{});
        window.CCCompletedChecks?.completed({id:run.id,ein:run.ein,states:run.states,apiBase:API_BASE,
          credentials:{email:account.email,admin_passcode:adminPasscode.value.trim(),device_id:account.device}});
      } catch(error) {
        stopElapsedTimer();
        if(runController?.signal.aborted && activeRecovery) {
          const saved=await finishRecovery(activeRecovery,error.partialResults||[],error.runStopped===true);
          if(saved.rows.length)renderResults(saved.rows);
        } else throw error;
      } finally {
        activeRecovery?.monitor.stop();
        activeRecovery=null;
        runController=null;
        stopRun.hidden=true;
        if(ownsConnector)await window.CCNYConnector.release();
        connectorPreflightPending=false;
        submitButton.disabled=namesRequired()&&!window.CCIdentity?.ready();
        window.CCIdentity.setBusy(false);
        void recoveryPanel.refresh();
      }
    }

    if (recoveryAPI) {
      recoveryPanel=recoveryAPI.mount(document.getElementById("auroraRecoveryStatus"),{
        account:recoveryAccount,resume:resumeSavedRecovery,view:rows=>renderResults(rows),error:showError});
      window.addEventListener("load", () => void recoveryPanel.refresh());
      email.addEventListener("change", () => void recoveryPanel.refresh());
      document.addEventListener("click", event => {
        if(event.target.closest?.("button")?.textContent.trim()==="Unlock staging")
          setTimeout(()=>void recoveryPanel.refresh(),0);
      }, true);
    }

    downloadExcelButton.addEventListener("click", downloadExcel);''')

    replace('      runController = window.CCOptimized && internalUnlocked ? new AbortController() : null;',
        '''      runController = window.CCOptimized && internalUnlocked ? new AbortController() : null;
      if (recoveryAPI && runController && states.length > 1) {
        const savedRun = recoveryAPI.make({name:organizationNameValue,ein:einValue,email:emailValue,
          device:getDeviceId(),states,aliases:runAlternateNames});
        activeRecovery = setupRecovery(savedRun,states);
        if (activeRecovery) {
          recoveryPanel.hide();
          void activeRecovery.saved.begin().catch(()=>{});
        }
      }''')
    replace('const results = await runStateChecks(states, einValue, emailValue, organizationNameValue, runController?.signal);',
        '''const check = () => runStateChecks(states, einValue, emailValue, organizationNameValue, runController?.signal, activeRecovery);
        const results = activeRecovery
          ? await recoveryAPI.exclusive(activeRecovery.run.owner,einValue,check) : await check();''')
    replace('        renderResults(results);\n        if(results.length===states.length)',
        '''        if (results.paused && activeRecovery) {
          const saved = await finishRecovery(activeRecovery,results.partialResults,results.cleanupConfirmed);
          if(saved.rows.length)renderResults(saved.rows);
          document.getElementById("progressLabel").textContent = saved.ready
            ? "Browser checks paused. You can restart Chrome and resume the remaining states."
            : results.cleanupConfirmed ? "Browser checks paused. Review the completed results below."
            : "Browser cleanup could not be confirmed. Review the completed results below.";
          return;
        }
        if(activeRecovery) {
          const {run,saved}=activeRecovery;
          void saved.finish("completed",results).then(()=>recoveryAPI.discard(run.id)).catch(()=>{});
        }
        renderResults(results);
        if(results.length===states.length)''')
    replace('          if (error.partialResults?.length) renderResults(error.partialResults);',
        '''          const partial = activeRecovery
            ? (await finishRecovery(activeRecovery,error.partialResults||[],error.runStopped===true)).rows
            : (error.partialResults||[]);
          if (partial.length) renderResults(partial);''')
    replace('          const completed = error.partialResults?.length || 0;', '          const completed = partial.length;')
    replace('        await window.CCNYConnector?.release();\n        runController = null;', '''        activeRecovery?.monitor.stop();
        activeRecovery=null;
        await window.CCNYConnector?.release();
        runController = null;
        void recoveryPanel?.refresh();''')
    return text
