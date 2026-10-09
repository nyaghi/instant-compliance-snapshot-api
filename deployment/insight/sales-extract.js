/* Trial-only, client-side Sales-format export of an already settled Standard snapshot. */
(() => {
  'use strict';
  const insightButton = document.getElementById('generateReportButton');
  if (!insightButton) return;
  const button = document.createElement('button');
  button.type = 'button';
  button.id = 'generateSalesExtractButton';
  button.className = 'hidden rounded-md border border-[#0B2A5B] bg-white px-4 py-2 text-xs font-semibold text-[#0B2A5B] hover:bg-slate-100 disabled:opacity-50';
  button.textContent = 'Generate Sales Report';
  button.title = 'Create a four-column Sales-format report from these completed Standard results. No new state checks run.';
  insightButton.after(button);
  const message = document.createElement('span');
  message.id = 'salesExtractMessage';
  message.setAttribute('role', 'status');
  message.className = 'text-xs text-slate-600';
  button.after(message);
  let snapshot = [];
  const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const einText = value => String(value ?? '').replace(/\D/g, '').replace(/^(\d{2})(\d{7})$/, '$1-$2');
  window.addEventListener('cc-standard-results', event => {
    snapshot = Array.isArray(event.detail?.results) ? event.detail.results.map(result => ({...result})) : [];
    button.classList.toggle('hidden', !snapshot.length);
    button.disabled = !snapshot.length;
    message.textContent = '';
  });
  button.addEventListener('click', () => {
    if (!snapshot.length || button.disabled || typeof window.CCSales?.displayStatus !== 'function') return;
    const started = performance.now();
    const rows = snapshot.map(result => `<tr><td>${escape(result.organization_name)}</td><td>${escape(einText(result.ein))}</td><td>${escape(result.state)}</td><td>${escape(window.CCSales.displayStatus(result))}</td></tr>`).join('');
    const organization = snapshot[0]?.organization_name || 'Organization';
    const ein = einText(snapshot[0]?.ein);
    const html = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CharityClarity Sales Report</title><style>body{font:15px Arial,sans-serif;background:#f3f6fa;color:#0B2A5B;margin:0;padding:36px}main{max-width:1000px;margin:auto;background:white;padding:32px;border:1px solid #dbe3ed;border-radius:12px}img{width:310px;max-width:100%;height:auto}h1{margin:18px 0 4px;font-size:24px}p{color:#475569}table{border-collapse:collapse;width:100%;margin-top:24px}th,td{text-align:left;padding:11px;border-bottom:1px solid #dbe3ed}th{background:#eef2f7;color:#0B2A5B}footer{font-size:12px;margin-top:24px;color:#475569}@media print{body{background:white;padding:0}main{border:0;padding:0}}</style></head><body><main><img src="${escape(new URL('/assets/charityclarity-aurora-20260928.png', location.origin).href)}" alt="CharityClarity Aurora"><h1>Sales Report</h1><p>${escape(organization)} · EIN ${escape(ein)}</p><p>Sales-format summary of completed Standard results. No additional registry searches were run.</p><table><thead><tr><th>Organization</th><th>EIN</th><th>State</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table><footer>CharityClarity provides an informational compliance snapshot. “Not Found” does not establish non-registration; confirm time-sensitive decisions with the state.</footer></main></body></html>`;
    const url = URL.createObjectURL(new Blob([html], {type:'text/html;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = `CharityClarity-Sales-Report-${String(ein).replace(/\D/g,'')}-${new Date().toISOString().slice(0,10)}.html`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    message.textContent = `Four-column report downloaded from the current Standard snapshot in ${Math.round(performance.now()-started)} ms. No new state checks ran.`;
  });
})();
