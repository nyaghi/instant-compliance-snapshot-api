/* Candidate identity decisions. Status interpretation remains in the master. */
(() => {
  'use strict';
  function add(parent, tag, value, classes = '') {
    const el = document.createElement(tag); el.textContent = value; el.className = classes; parent.appendChild(el); return el;
  }
  function render(parent, result, decide, retry) {
    const review = result.identity_review;
    const inconclusive = ['Needs Review', 'Unable to Confirm', 'Site Not Reachable', 'No Confirmed Match'].includes(result.status);
    if (!review?.candidates?.length && !inconclusive) return;
    const box = add(parent, 'div', '', 'mt-3 border-t border-slate-200 pt-3 whitespace-normal');
    const message = add(box, 'p', '', 'text-sm text-slate-600'); message.setAttribute('role', 'status');
    const buttons = [];
    let busy = false;
    function action(parent, label, run) {
      const button = add(parent, 'button', label, 'rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-100 disabled:opacity-50');
      button.type = 'button'; buttons.push(button);
      button.addEventListener('click', async () => {
        if (busy) return; busy = true; buttons.forEach(b => b.disabled = true); message.textContent = 'Updating this state result…';
        try { await run(); }
        catch (error) { message.textContent = error.message || 'The update could not finish. The original result is retained.'; }
        finally { busy = false; buttons.forEach(b => b.disabled = false); }
      });
    }
    if (review?.candidates?.length) {
      add(box, 'p', 'Confirm the organization', 'font-semibold text-slate-900');
      add(box, 'p', 'Accept or reject the identity. CharityClarity calculates the status from the state record. This decision applies to this snapshot.', 'mt-1 text-xs text-slate-600');
      for (const candidate of review.candidates) {
        const card = add(box, 'div', '', 'mt-3 rounded-md border border-slate-200 p-3');
        add(card, 'p', candidate.name, 'font-semibold');
        add(card, 'p', [candidate.identifier, candidate.location].filter(Boolean).join(' · '), 'mt-1 text-xs');
        add(card, 'p', [candidate.raw_status, candidate.expiration ? `Expiration: ${candidate.expiration}` : ''].filter(Boolean).join(' · '), 'mt-1 text-xs text-slate-600');
        try {
          const url = new URL(candidate.source_url);
          if (url.protocol === 'https:') {
            const link = add(card, 'a', 'View state record', 'mt-1 inline-block text-xs underline');
            link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
          }
        } catch { /* No public link was supplied. */ }
        if (candidate.decision) add(card, 'p', candidate.decision === 'accept' ? 'Identity accepted by user' : 'Identity rejected by user', 'mt-2 text-xs font-semibold');
        const controls = add(card, 'div', '', 'mt-2 flex flex-wrap gap-2');
        action(controls, 'Accept match', () => decide(candidate.id, 'accept'));
        action(controls, 'Reject match', () => decide(candidate.id, 'reject'));
        if (candidate.decision) action(controls, 'Undo decision', () => decide(candidate.id, 'clear'));
      }
    }
    if (inconclusive) {
      const controls = add(box, 'div', '', 'mt-3');
      action(controls, `Retry ${result.state}`, retry);
    }
  }
  window.CCIdentityReview = Object.freeze({render});
})();
