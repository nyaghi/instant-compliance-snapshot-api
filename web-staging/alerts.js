(() => {
  const $ = id => document.getElementById(id);
  const page = $('alerts');
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
    local.failures = [{name:'Sample Learning Fund',state:'NJ',checked:time,failure:'Registry unavailable or result unconfirmed'}];
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
    for(const values of rows){const row=el('tr');for(const v of values)row.append(el('td',v));b.append(row);}
    t.append(h,b);wrap.append(t);return wrap;
  }
  function render() {
    $('account-view').hidden=false;
    $('example-label').hidden=!demo;
    badge(model.unseen);
    const output=$('changes');
    output.replaceChildren();
    if(!model.changes.length) output.append(el('p','No status changes to review.'));
    for(const dir of Object.keys(labels)){
      const group=model.changes.filter(x=>x.direction===dir);
      if(!group.length)continue;
      output.append(el('h3',labels[dir]));
      const byOrg=new Map();
      for(const x of group){if(!byOrg.has(x.ein))byOrg.set(x.ein,[]);byOrg.get(x.ein).push(x);}
      for(const rows of byOrg.values()){
        output.append(el('h4',rows[0].name));
        for(const x of rows){
          const row=el('div',null,'alert-row');
          row.append(el('strong',x.state),el('span',x.previous+' → '+x.status),el('span',time(x.checked),'muted'));
          if(!demo){const link=el('a','View evidence');link.href='/api/alerts/evidence/'+x.id;link.target='_blank';link.rel='noopener';row.append(link);}
          if(!x.seen){
            row.append(el('span','New','alert-new'));
            const button=el('button','Mark seen');button.type='button';
            button.setAttribute('aria-label','Mark '+x.name+' '+x.state+' change seen');
            button.onclick=async()=>{
              button.disabled=true;
              try {const data=await api('/api/alerts/seen',{id:x.id});x.seen=Date.now()/1000;model.unseen=data.unseen;render();}
              catch(err){report(err.message);button.disabled=false;}
            };
            row.append(button);
          }else row.append(el('span','Seen','muted'));
          output.append(row);
        }
      }
    }
    $('more').hidden=!model.next;
    $('organizations').replaceChildren(model.organizations.length ? table(
      ['Organization','EIN','Baseline','Last checked'],
      model.organizations.map(x=>[x.name,ein(x.ein),x.checking?'Checking now': x.confirmed===model.states?'Confirmed':x.confirmed+' / '+model.states+' states confirmed',time(x.last_checked)])
    ):el('p','Add an organization to start monitoring.'));
    $('failures').replaceChildren(model.failures.length ? table(['Organization','State','Checked','Issue'],
      model.failures.map(x=>[x.name,x.state,time(x.checked),x.failure])):el('p','No failed checks recorded.'));
  }
  async function load() {model=await api('/api/alerts');render();}
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
        labels[x.direction],new Date(x.checked*1000).toISOString(),x.seen?'Seen':'Unseen',
        demo?'':new URL('/api/alerts/evidence/'+x.id,location.origin).href]));
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
    }catch(err){report(err.message);}
  })();
  window.addEventListener('focus',()=>{if(model && !demo && $('enroll').hidden)void load().catch(()=>{});});
})();
