/* Opt-in presentation only on the isolated Performance Lab. */
(() => {
  if (location.origin !== 'https://charityclarity-final-four-29-2.onrender.com'
      || !['/', '/connector/final-four-validation.html'].includes(location.pathname)
      || new URLSearchParams(location.search).get('collector_layout') !== 'duo') return;

  const style = document.createElement('style');
  style.id = 'cc-two-window-trial-style';
  style.textContent = `
    @media (min-width: 1600px) {
      body:has(#appShell:not(.hidden)) { background: #eaf0f7 !important; }
      #appShell { width: 820px !important; max-width: 820px !important;
        margin-left: 0 !important; margin-right: auto !important;
        position: relative !important; z-index: 1 !important;
        background: #fff !important; border-right: 1px solid #c7d6e6 !important;
        box-shadow: 8px 0 26px #11365b12 !important; }
      #appShell main > section.bg-white > div:first-child {
        display: grid !important; grid-template-columns: minmax(0,1fr) !important;
        max-width: 100% !important; gap: 24px !important; }
      #appShell #resultPanel { width: 100% !important; max-width: 100% !important;
        margin-left: 0 !important; }
      body:has(#appShell:not(.hidden)) #ccCollectorRail { display: block !important; position: fixed !important;
        left: 820px; right: 0; top: 0; bottom: 0; z-index: 0;
        pointer-events: none; overflow: hidden;
        background: linear-gradient(160deg,#f2f7fc 0%,#e6eef7 100%);
        color: #12395e; font-family: inherit; }
      #ccCollectorRail .cc-rail-head { height: 64px; box-sizing: border-box;
        display: flex; justify-content: space-between; align-items: center;
        padding: 10px 18px 8px; border-bottom: 1px solid #ccd9e8; }
      #ccCollectorRail .cc-rail-title { font-size: 15px; font-weight: 750;
        letter-spacing: .01em; line-height: 1.25; }
      #ccCollectorRail .cc-rail-kicker { font-size: 10px; font-weight: 700;
        letter-spacing: .15em; color: #5f7790; text-transform: uppercase; }
      #ccCollectorRail .cc-rail-brand { font-size: 10px; line-height: 1.45;
        color: #58718b; text-align: right; }
      #ccCollectorRail .cc-rail-empty { max-width: 440px; margin: 94px auto 0;
        padding: 0 28px; text-align: center; color: #58718b;
        font-size: 14px; line-height: 1.55; }
      #ccCollectorRail .cc-rail-empty::before { content: ''; display: block;
        width: 42px; height: 4px; margin: 0 auto 19px; border-radius: 4px;
        background: #c42b31; }
      #ccCollectorRail .cc-rail-empty strong { display: block;
        margin-bottom: 5px; color: #12395e; font-size: 16px; }
      /* Once a run finishes, return the full page width to the results table. */
      body:has(#ccStandardMode[aria-pressed="true"]):has(#resultPanel:not(.hidden)):has(#resultElapsed:not(:empty)):has(#submitButton:not(:disabled)),
      body:has(#ccSalesMode[aria-pressed="true"]):has(#ccSalesResults:not([hidden])):has(#ccSalesRun:not(:disabled))
        { background: #fff !important; }
      body:has(#ccStandardMode[aria-pressed="true"]):has(#resultPanel:not(.hidden)):has(#resultElapsed:not(:empty)):has(#submitButton:not(:disabled)) #appShell,
      body:has(#ccSalesMode[aria-pressed="true"]):has(#ccSalesResults:not([hidden])):has(#ccSalesRun:not(:disabled)) #appShell
        { width: 100% !important; max-width: none !important;
          border-right: 0 !important; box-shadow: none !important; }
      body:has(#ccStandardMode[aria-pressed="true"]):has(#resultPanel:not(.hidden)):has(#resultElapsed:not(:empty)):has(#submitButton:not(:disabled)) #ccCollectorRail,
      body:has(#ccSalesMode[aria-pressed="true"]):has(#ccSalesResults:not([hidden])):has(#ccSalesRun:not(:disabled)) #ccCollectorRail
        { display: none !important; }
    }
  `;
  (document.head || document.documentElement).appendChild(style);

  const mount = () => {
    if (document.getElementById('ccCollectorRail')) return;
    const rail = document.createElement('aside');
    rail.id = 'ccCollectorRail';
    rail.setAttribute('aria-hidden', 'true');
    rail.style.display = 'none';
    rail.innerHTML = '<div class="cc-rail-head"><div><div class="cc-rail-kicker">CharityClarity Aurora</div><div class="cc-rail-title">Live state registries</div></div><div class="cc-rail-brand">Compliance Express<br>www.compliance-express.com</div></div><div class="cc-rail-empty"><strong>Public records, alongside your results</strong>Registry pages appear in this workspace while CharityClarity checks the states you selected.</div>';
    document.body.appendChild(rail);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount, {once:true});
  else mount();
})();
