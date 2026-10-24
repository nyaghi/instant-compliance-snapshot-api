/* Candidate identity decisions. Status interpretation remains in the master. */
(() => {
  'use strict';
  function add(parent, tag, value, classes = '') {
    const el = document.createElement(tag); el.textContent = value; el.className = classes; parent.appendChild(el); return el;
  }
  function renderEvidence(parent, result) {
    const source = /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(result.evidence_url || '');
    const bundle = /^\/state-evidence\/([a-f0-9]{64})\/evidence\.zip$/.exec(result.evidence_bundle_url || '');
    const history = /^\/state-evidence\/([a-f0-9]{64})\/search-history\.pdf$/.exec(result.search_history_url || '');
    const validHistory = history && (!result.evidence_bundle_url || bundle && bundle[1] === history[1]);
    if (validHistory && (result.identity_review_evidence_final === true || result.success === true && (result.status === 'Not Registered' || result.state === 'IL' && result.status === 'Not Registered / Non-Compliant'))) {
      const log = add(parent, 'a', 'View Search History (PDF)', 'mt-2 block text-xs underline whitespace-normal');
      log.href = '/evidence-preview.html?document=' + encodeURIComponent(result.search_history_url); log.target = '_blank'; log.rel = 'noopener noreferrer';
    }
    // A completed absence is documented by actual queries, not an empty image.
    // An identified record whose official status is Unregistered keeps its image.
    const negative = result.success === true && (result.status === 'Not Registered'
      || result.state === 'IL' && result.status === 'Not Registered / Non-Compliant');
    const matched = !!(result.matched_registry_identifier || result.identifier
      || result.matched_registry_name);
    if (negative && (result.identity_review_evidence_final === true || !matched)) {
      if (!validHistory) add(parent,'p','Search history unavailable for this check.','mt-2 text-xs text-slate-500 whitespace-normal');
      return;
    }
    if (!source) {
      const candidateSnapshots = result.state === 'DC' && result.identity_review?.candidates?.length
        && result.identity_review.candidates.every(candidate => /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(candidate.evidence_url || ''));
      if (candidateSnapshots) add(parent,'p','View the state snapshots in the candidate records below.','mt-2 text-xs text-slate-500 whitespace-normal');
      else if (result.evidence_capture === 'unavailable') add(parent,'p',result.state === 'TN' && result.matched_registry_identifier ? 'Detail snapshot unavailable for this check.' : 'State snapshot unavailable for this check.','mt-2 text-xs text-slate-500 whitespace-normal');
      return;
    }
    const link = add(parent, 'a', 'View State Snapshot (PDF)', 'mt-2 block text-xs underline whitespace-normal');
    link.href = '/evidence-preview.html?document=' + encodeURIComponent(result.evidence_url); link.target = '_blank'; link.rel = 'noopener noreferrer';
  }
  function render(parent, result, decide, retry) {
    const review = result.identity_review;
    const inconclusive = ['Needs Review', 'Unable to Confirm', 'Site Not Reachable', 'No Confirmed Match'].includes(result.status);
    if (!review?.candidates?.length && !inconclusive) return;
    const box = add(parent, 'div', '', 'mt-3 border-t border-slate-200 pt-3 whitespace-normal');
    const message = add(box, 'p', '', 'text-sm text-slate-600'); message.setAttribute('role', 'status');
    const buttons = [];
    let busy = false;
    function action(parent, label, run, selected = false) {
      const button = add(parent, 'button', label, 'rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-100 disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed disabled:opacity-50');
      button.type = 'button'; button.disabled = selected; buttons.push({button, selected});
      button.addEventListener('click', async () => {
        if (busy || button.disabled) return; busy = true; buttons.forEach(({button}) => button.disabled = true); message.textContent = 'Updating this state result…';
        try { await run(); }
        catch (error) { message.textContent = error.message || 'The update could not finish. The original result is retained.'; }
        finally { busy = false; buttons.forEach(({button, selected}) => button.disabled = selected); }
      });
      return button;
    }
    if (review?.candidates?.length) {
      add(box, 'p', 'Confirm the organization', 'font-semibold text-slate-900');
      add(box, 'p', review.exclusive
        ? (review.candidates.length > 1
          ? 'The registry returned multiple possible organization records. Choose the record that belongs to your organization. No status is applied until you confirm its identity.'
          : 'The registry returned a possible organization record. Confirm whether it belongs to your organization. No status is applied until you confirm its identity.')
        : 'Accept or reject the identity. CharityClarity Aurora calculates the status from the state record. This decision applies to this snapshot.', 'mt-1 text-xs text-slate-600');
      for (const candidate of review.candidates) {
        const card = add(box, 'div', '', 'mt-3 rounded-md border border-slate-200 p-3');
        if (review.exclusive && candidate.suggested) add(card, 'p', 'Suggested match · confirm before using its status', 'mb-1 text-xs font-semibold text-slate-900');
        add(card, 'p', candidate.name, 'font-semibold');
        add(card, 'p', [candidate.identifier, candidate.location].filter(Boolean).join(' · '), 'mt-1 text-xs');
        add(card, 'p', [candidate.raw_status, candidate.expiration ? `Expiration: ${candidate.expiration}` : ''].filter(Boolean).join(' · '), 'mt-1 text-xs text-slate-600');
        renderEvidence(card, candidate);
        if (candidate.decision) add(card, 'p', candidate.decision === 'accept' ? 'Identity accepted by user' : 'Identity rejected by user', 'mt-2 text-xs font-semibold');
        const controls = add(card, 'div', '', 'mt-2 flex flex-wrap gap-2');
        action(controls, review.exclusive ? 'Confirm this record' : 'Accept match', () => decide(candidate.id, 'accept'), candidate.decision === 'accept').setAttribute('aria-pressed', String(candidate.decision === 'accept'));
        action(controls, 'Reject match', () => decide(candidate.id, 'reject'), candidate.decision === 'reject').setAttribute('aria-pressed', String(candidate.decision === 'reject'));
        if (candidate.decision) action(controls, 'Undo match', () => decide(candidate.id, 'clear'));
      }
    }
    if (inconclusive && (!review?.candidates?.some(candidate => candidate.decision)
        || result.state === 'NC' && review.search_complete === false
          && review.candidates.some(candidate => candidate.decision === 'reject'))) {
      const controls = add(box, 'div', '', 'mt-3');
      action(controls, `Retry ${result.state}`, retry);
    }
  }
  function statusLabel(result) {
    const inconclusive = ['Needs Review', 'Unable to Confirm', 'Site Not Reachable', 'No Confirmed Match'].includes(result.status);
    if (inconclusive && result.identity_review?.candidates?.some(candidate => !candidate.decision)) return 'Confirm match';
    return result.status === 'Needs Review' ? 'Unable to Confirm' : result.status || 'Unknown';
  }
  window.CCIdentityReview = Object.freeze({render, renderEvidence, statusLabel});
})();
