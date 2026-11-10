(() => {
  const $ = id => document.getElementById(id);
  const page = $('alerts');
  $('returnToAurora')?.addEventListener('click', event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    try {
      const aurora = window.opener;
      if (!aurora || aurora.closed || aurora.location.origin !== location.origin
          || !aurora.document.getElementById('snapshotForm')) return;
      aurora.focus();
      window.close();
      event.preventDefault();
    } catch { /* Direct visits and cross-origin openers use the ordinary link. */ }
  });
  const demo = !!page && new URLSearchParams(location.search).get('example') === '1';
  const labels = {adverse:'Needs attention', favorable:'Favorable changes', other:'Other changes'};
  const local = {organizations: [], changes: [], failures: [], unseen: 0, states: 38, next:null};
  if (demo) {
    const time = Date.now()/1000;
    const seen = new Set(JSON.parse(sessionStorage.getItem('cc.alerts.example.seen') || '[]'));
    local.changes = [
      {id:1,name:'Sample Community Foundation',ein:'012345678',state:'NY',previous:'Current',status:'Delinquent',direction:'adverse',checked:time},
      {id:2,name:'Sample Community Foundation',ein:'012345678',state:'NJ',previous:'Upcoming Filing',status:'Current',direction:'favorable',checked:time},
      {id:3,name:'Sample Learning Fund',ein:'012345679',state:'CA',previous:'Pending',status:'Current',direction:'favorable',checked:time}
    ].map(x => ({...x,seen:seen.has(x.id)?time:null}));
    local.organizations = [
      {name:'Sample Community Foundation',ein:'012345678',confirmed:38,last_checked:time},
      {name:'Sample Learning Fund',ein:'012345679',confirmed:37,last_checked:time}
    ];
    local.failures = [{name:'Sample Learning Fund',ein:'012345679',state:'NJ',checked:time,failure:'Registry unavailable or result unconfirmed'}];
    local.unseen = local.changes.filter(x => !x.seen).length;
  }

  async function api(path, data) {
    if (demo) {
      if (path.endsWith('/seen')) {
        const change = local.changes.find(x => x.id === data.id);
        if (change && !change.seen) change.seen = Date.now()/1000;
        sessionStorage.setItem('cc.alerts.example.seen',JSON.stringify(local.changes.filter(x=>x.seen).map(x=>x.id)));
        local.unseen = local.changes.filter(x => !x.seen).length;
      }
      if (path.endsWith('/organizations/remove')) {
        const length=local.organizations.length;
        local.organizations=local.organizations.filter(x=>x.ein!==data.ein);
        return {removed:local.organizations.length<length};
      }
      if (path.endsWith('/organizations')) {
        const ein=data.ein.replace(/\D/g,'');
        if (local.organizations.some(x=>x.ein===ein)) return {added:false};
        local.organizations.push({name:data.name,ein,confirmed:0,last_checked:null});
        return {added:true};
      }
      return local;
    }
    const response = await fetch(path,{cache:'no-store',credentials:'same-origin',
      ...(data && {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})});
    if (!response.ok) {
      let text = response.status === 401 ? 'Open Alerts from your signed-in CharityClarity account.' : 'Alerts are temporarily unavailable.';
      try { if(response.status!==401) text=(await response.json()).error || text; } catch {}
      throw Error(text);
    }
    return response.json();
  }
  const el=(tag,text,cls) => {const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const time = v => v ? new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(v*1000)) : '—';
  const ein = v => v.slice(0,2)+'-'+v.slice(2);
  const report = msg => {if(page) $('message').textContent=msg;};

  function badge(n) {
    for (const link of document.querySelectorAll('[data-cc-alerts-link]')) {
      const count=link.querySelector('.cc-alert-count');
      if (!count) continue;
      count.textContent=String(n);
      count.hidden=!(n>0);
      link.setAttribute('aria-label',n>0? 'CharityClarity Alerts, '+n+' new':'CharityClarity Alerts');
    }
  }
  async function refreshBadge() {try { badge((await api('/api/alerts/badge')).unseen); } catch { badge(0); }}
  if(!page){void refreshBadge();window.addEventListener('focus',refreshBadge);window.addEventListener('pageshow',refreshBadge);
    setInterval(()=>{if(!document.hidden)void refreshBadge();},60000);return;}

  let model = null;
  function table(head,rows) {
    const wrap=el('div',null,'table-scroll'), t=el('table'), h=el('thead'), b=el('tbody'), r=el('tr');
    for(const v of head){const c=el('th',v);c.scope='col';r.append(c);}
    h.append(r);
    for(const values of rows){
      const row=el('tr');
      for(const value of values){
        const cell=el('td');
        cell.append(value);
        row.append(cell);
      }
      b.append(row);
    }
    t.append(h,b);wrap.append(t);return wrap;
  }
  function matchLabel(name, identifier) {
    const sourceId = identifier && !identifier.startsWith('ar-name:');
    return 'Automatically accepted' + (name ? ': ' + name : '') + (sourceId ? ' (' + identifier + ')' : '');
  }

  function render() {
    $('account-view').hidden=false;
    $('example-label').hidden=!demo;
    badge(model.unseen);
    const output=$('changes');
    output.replaceChildren();
    for(const dir of Object.keys(labels)){
      const group=model.changes.filter(x=>x.direction===dir);
      if(dir==='other' && !group.length)continue;
      const card=el('section',null,'alert-change-card alert-change-'+dir);
      const title=el('h3',labels[dir]);
      title.id='alert-change-title-'+dir;
      card.setAttribute('aria-labelledby',title.id);
      card.append(title);
      output.append(card);
      if(!group.length){
        card.append(el('p',dir==='adverse'?'No changes need attention.':'No favorable changes.','muted'));
        continue;
      }
      const byOrg=new Map();
      for(const x of group){if(!byOrg.has(x.ein))byOrg.set(x.ein,[]);byOrg.get(x.ein).push(x);}
      for(const rows of byOrg.values()){
        card.append(el('h4',rows[0].name));
        for(const x of rows){
          const row=el('div',null,'alert-row');
          row.append(el('strong',x.state),el('span',x.previous+' → '+x.status),el('span',time(x.checked),'muted'));
          if(x.corrected){
            row.append(el('span','Match corrected','muted'));
          }else if(x.automatic){
            row.append(el('span',matchLabel(x.match_name, x.match_identifier),'muted'));
          }
          if(!x.seen && !x.corrected){
            row.append(el('span','New','alert-new'));
            const button=el('button','Mark seen');button.type='button';
            button.setAttribute('aria-label','Mark '+x.name+' '+x.state+' change seen');
            button.onclick=async()=>{
              button.disabled=true;
              try {const data=await api('/api/alerts/seen',{id:x.id});x.seen=Date.now()/1000;model.unseen=data.unseen;render();}
              catch(err){report(err.message);button.disabled=false;}
            };
            row.append(button);
          }else if(!x.corrected)row.append(el('span','Seen','muted'));
          card.append(row);
        }
      }
    }
    $('more').hidden=!model.next;
    $('organizations').replaceChildren(model.organizations.length ? table(
      ['Organization','EIN','Last checked','Coverage'],
      model.organizations.map(x=>{
        const missing=(model.failures || []).filter(issue=>issue.ein===x.ein).map(issue=>issue.state);
        const coverage=x.checking?'Checking now':!x.last_checked?'First check queued':
          missing.length?'Awaiting a result in '+[...new Set(missing)].sort().join(', '):'';
        const organization=el('div',null,'monitored-org-name');
        const remove=el('button','Remove');
        remove.type='button';
        remove.setAttribute('aria-label','Remove '+x.name+' ('+ein(x.ein)+') from monitoring');
        remove.onclick=async()=>{
          if(!window.confirm('Stop monitoring '+x.name+'? Recent alerts will stay in your history.'))return;
          remove.disabled=true;
          try{
            const result=await api('/api/alerts/organizations/remove',{ein:x.ein});
            await load();
            report(result.removed?'Monitoring stopped for '+x.name+'.':'This organization is already removed.');
          }catch(err){report(err.message);remove.disabled=false;}
        };
        organization.append(el('span',x.name),remove);
        return [organization,ein(x.ein),time(x.last_checked),coverage];
      })
    ):el('p','Add an organization to start monitoring.'));
    const matches=$('matches');
    matches.replaceChildren();
    $('automatic-matches').hidden=!model.matches?.length;
    for(const match of model.matches || []){
      const row=el('div',null,'alert-row');
      const org=model.organizations.find(x=>x.ein===match.ein);
      row.append(el('strong',match.state),el('span',org?.name || ein(match.ein)),
        el('span',matchLabel(match.name, match.identifier),'muted'),el('span',match.status || 'Status not confirmed'));
      if(match.has_evidence){
        const evidence=el('a','View evidence');
        evidence.href='/api/alerts/match-evidence/'+match.ein+'/'+match.state;
        evidence.target='_blank';evidence.rel='noopener';
        row.append(evidence);
      }
      const action=el('button','Change match');
      const controls=el('div');
      controls.hidden=true;
      const reject=el('button','Reject this match');
      reject.type=action.type='button';
      action.setAttribute('aria-expanded','false');
      action.onclick=()=>{
        controls.hidden=!controls.hidden;
        action.setAttribute('aria-expanded',String(!controls.hidden));
      };
      reject.onclick=async()=>{
        reject.disabled=true;
        try{
          const {ein,state,identifier,workflow}=match;
          await api('/api/alerts/change-match',{ein,state,identifier,workflow});
          await load();
          report('Match rejected. A new check is queued.');
        }catch(err){report(err.message);reject.disabled=false;}
      };
      controls.append(el('p','Reject this record and check the state again.'),reject);
      row.append(action,controls);
      matches.append(row);
    }
  }
  async function load() {model=await api('/api/alerts');render();}
  const background=$('background');
  async function browserSetting(){
    if(demo || !window.CCAlertsBrowser)return;
    const setting=await window.CCAlertsBrowser('status');
    const ready=setting.ok && setting.quiet === true;
    background.hidden=!ready;
    $('background-status').textContent=!ready?'Update the CharityClarity Chrome connector to enable background checks.':
      setting.enabled?'Automatic checks use background tabs while this Chrome profile is open.':
      'Enable automatic checks on this computer.';
    if(!ready)return;
    background.textContent=setting.enabled?'Pause automatic checks in this browser':'Enable automatic checks in this browser';
    background.onclick=async()=>{
      background.disabled=true;
      try{
        const profile=setting.enabled?null:(await api('/api/alerts/runner/enable',{})).profile;
        const changed=await window.CCAlertsBrowser(setting.enabled?'disable':'enable',profile);
        if(!changed.ok)throw Error('Chrome could not change this setting. Try again.');
        await browserSetting();
      }catch(err){report(err.message);}
      finally{background.disabled=false;}
    };
  }
  $('add').onclick=()=>{
    const form=$('enroll');
    form.hidden=!form.hidden;
    $('add').setAttribute('aria-expanded',String(!form.hidden));
    if(!form.hidden)form.elements.name.focus();
  };
  $('enroll').onsubmit=async event=>{
    event.preventDefault();
    const form=event.currentTarget, button=form.querySelector('button');
    const data=Object.fromEntries(new FormData(form));
    button.disabled=true;
    try {
      const result=await api('/api/alerts/organizations',data);
      form.reset();form.hidden=true;$('add').setAttribute('aria-expanded','false');
      await load();report(result.added?'Organization added. Its baseline check is queued.':'This EIN is already monitored.');
    } catch(err){report(err.message);}
    finally {button.disabled=false;}
  };
  $('more').onclick=async()=>{
    try {const batch=await api('/api/alerts?before='+model.next);model.changes.push(...batch.changes);model.next=batch.next;render();}
    catch(err){report(err.message);}
  };
  $('download').onclick=async()=>{
    const button=$('download');button.disabled=true;
    try{
      let batch=await api('/api/alerts');const rows=[...batch.changes];
      while(batch.next){batch=await api('/api/alerts?before='+batch.next);rows.push(...batch.changes);}
      const workbook=window.CCExcelExport.buildAlerts(rows.map(x=>[x.name,ein(x.ein),x.state,x.previous,x.status,
        labels[x.direction],new Date(x.checked*1000).toISOString(),x.corrected?'Match corrected':x.seen?'Seen':'Unseen',
        !demo && x.has_evidence ? new URL('/api/alerts/evidence/'+x.id,location.origin).href : '']));
      const href=URL.createObjectURL(workbook), a=el('a');
      a.href=href;a.download='CharityClarity-Alerts.xlsx';a.click();
      setTimeout(()=>URL.revokeObjectURL(href),10000);
    } catch(err){report(err.message);}
    finally{button.disabled=false;}
  };
  (async()=>{
    try{
      const fragment=new URLSearchParams(location.hash.slice(1)), claim=fragment.get('account-session');
      if(claim && !demo){history.replaceState(null,'',location.pathname+location.search);await api('/api/alerts/session',{claim});}
      await load();
      await browserSetting();
    }catch(err){report(err.message);}
  })();
  window.addEventListener('focus',()=>{if(model && !demo && $('enroll').hidden)void load().catch(()=>{});});
})();
