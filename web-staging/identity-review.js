/* Candidate identity decisions. Status interpretation remains in the master. */
(() => {
  'use strict';
  const unresolvedStatuses = new Set(['Needs Review', 'Unable to Confirm', 'Unable to Verify', 'Site Not Reachable', 'No Confirmed Match', 'Unknown']);
  function selectedCANonregistration(result) {
    const raw = result.raw_status_text || '';
    return result.state === 'CA' && result.success === true && result.status === 'Not Registered'
      && !!result.matched_registry_name && /^\d+$/.test(result.matched_registry_identifier || '')
      && !result.computed_due_date
      && /(?:^|\|)\s*Registration Type:\s*Charitable Organization\s*(?:\||$)/i.test(raw)
      && /(?:^|\|)\s*Registration Status:\s*Not Registered\s*(?:\||$)/i.test(raw)
      && !/\b(?:suspended|revoked|enforcement|cease\s+and\s+desist)\b/i.test(raw);
  }
  function boundedSourceFailure(result) {
    return result.status === 'Site Not Reachable' && !result.identity_review?.candidates?.length
      && (result.state === 'OR' && ['OR_SOURCE_UNREACHABLE', 'OR_SOURCE_ACCESS_REFUSED', 'OR_SOURCE_TIME_LIMIT'].includes(result.reason_code)
        || result.state === 'NM' && result.status_reason === 'NY_CONNECTOR_REGISTRY_NM_HTTP_ERROR'
        || result.state === 'NV' && ['NY_CONNECTOR_REGISTRY_NV_STARTUP_UNREACHABLE','NY_CONNECTOR_REGISTRY_NV_FORM_LOAD_TIMEOUT','NY_CONNECTOR_REGISTRY_NV_SEARCH_RESPONSE_TIMEOUT','NY_CONNECTOR_REGISTRY_NV_LOOKUP_TIMEOUT','NY_CONNECTOR_REGISTRY_NV_SEARCH_SOURCE_ERROR'].includes(result.status_reason)
        || result.state === 'DC' && result.reason_code === 'DC_LICENSE_SOURCE_UNREACHABLE'
        || result.state === 'WI' && ['WI_SOURCE_UNREACHABLE', 'WI_SOURCE_ALLOWANCE_EXHAUSTED'].includes(result.reason_code)
        || result.state === 'FL' && result.reason_code === 'FL_INCOMPLETE_SEARCH'
        || ['ND','CO'].includes(result.state) && result.reason_code === 'RUNNER_TIMEOUT');
  }
  function add(parent, tag, value, classes = '') {
    const el = document.createElement(tag); el.textContent = value; el.className = classes; parent.appendChild(el); return el;
  }
  function usesSearchHistoryOnly(result) {
    const completedNegative = result.success === true && (result.status === 'Not Registered'
      || result.state === 'IL' && result.status === 'Not Registered / Non-Compliant');
    const candidates = result.identity_review?.candidates;
    const allRejected = candidates?.length > 0 && candidates.every(candidate => candidate.decision === 'reject');
    return completedNegative && !selectedCANonregistration(result)
      || result.identity_review_evidence_final === true && allRejected;
  }
  function renderEvidence(parent, result) {
    const source = /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(result.evidence_url || '');
    const bundle = /^\/state-evidence\/([a-f0-9]{64})\/evidence\.zip$/.exec(result.evidence_bundle_url || '');
    const history = /^\/state-evidence\/([a-f0-9]{64})\/search-history\.pdf$/.exec(result.search_history_url || '');
    const validHistory = history && (!result.evidence_bundle_url || bundle && bundle[1] === history[1]);
    const incompleteAttempts = result.success === false && (
      result.state === 'AR' && result.status_reason === 'AR_REQUIRED_SEARCH_INCOMPLETE'
      || result.state === 'NC' && result.status_reason === 'NY_CONNECTOR_NC_RATE_LIMITED');
    if (validHistory && (incompleteAttempts || result.identity_review_evidence_final === true || result.success === true && (result.status === 'Not Registered' || result.state === 'IL' && result.status === 'Not Registered / Non-Compliant'))) {
      const namesOnly = result.state === 'CT' && result.rejected_search_history === true || result.success === true && (result.status === 'Not Registered' || result.state === 'IL' && result.status === 'Not Registered / Non-Compliant');
      const log = add(parent, 'a', incompleteAttempts ? 'View Search Attempts (PDF)' : namesOnly ? 'View Names Searched (PDF)' : 'View Search History (PDF)', 'mt-2 block text-xs underline whitespace-normal');
      log.href = '/evidence-preview.html?document=' + encodeURIComponent(result.search_history_url); log.target = '_blank'; log.rel = 'noopener noreferrer';
    }
    // A completed absence is documented by actual queries, not an empty image.
    if (usesSearchHistoryOnly(result)) {
      if (!validHistory) add(parent,'p','Names searched unavailable for this check.','mt-2 text-xs text-slate-500 whitespace-normal');
      return;
    }
    // During a multi-candidate review, keep the status decision pending,
    // but make each explicitly accepted original available in the main comments.
    const candidates = result.identity_review?.candidates;
    const accepted = candidates && candidates.filter(candidate => candidate.decision === 'accept');
    const unresolved = ['Needs Review', 'Unable to Confirm', 'Confirm Match'].includes(result.status);
    if (accepted?.length && (candidates.some(candidate => !candidate.decision) || unresolved)) {
      for (const candidate of accepted) {
        if (/^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(candidate.evidence_url || '')) {
          const link = add(parent, 'a', `View State Snapshot (PDF) — ${candidate.name} (identity accepted)`, 'mt-2 block text-xs underline whitespace-normal');
          link.href = '/evidence-preview.html?document=' + encodeURIComponent(candidate.evidence_url);
          link.target = '_blank'; link.rel = 'noopener noreferrer';
        } else {
          add(parent, 'p', `State snapshot unavailable for ${candidate.name} (identity accepted).`, 'mt-2 text-xs text-slate-500 whitespace-normal');
        }
      }
      return;
    }
    if (!source) {
      const candidateSnapshots = result.identity_review?.candidates?.length
        && result.identity_review.candidates.every(candidate => /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(candidate.evidence_url || ''));
      if (candidateSnapshots) add(parent,'p','View the state snapshots in the candidate records below.','mt-2 text-xs text-slate-500 whitespace-normal');
      else if (result.evidence_capture === 'unavailable') add(parent,'p',result.state === 'TN' && result.matched_registry_identifier ? 'Detail snapshot unavailable for this check.' : 'State snapshot unavailable for this check.','mt-2 text-xs text-slate-500 whitespace-normal');
      return;
    }
    const link = add(parent, 'a', 'View State Snapshot (PDF)', 'mt-2 block text-xs underline whitespace-normal');
    link.href = '/evidence-preview.html?document=' + encodeURIComponent(result.evidence_url); link.target = '_blank'; link.rel = 'noopener noreferrer';
  }
  function maActivityOnly(result) {
    const source = result.ma_filing_evidence;
    return result.state === 'MA' && result.status === 'Unable to Confirm'
      && ['MA_FORM_PC_DETAIL_UNCONFIRMED', 'MA_FORM_PC_ATTACHMENT_IDENTITY_CONFLICT'].includes(result.status_reason)
      && !result.identity_review?.candidates?.length && /^\d+$/.test(result.matched_registry_identifier || '')
      && source?.ago_account === result.matched_registry_identifier
      && source.registry_status?.trim().toLowerCase() === 'not doing business in mass';
  }
  function render(parent, result, decide, retry) {
    const review = result.identity_review;
    const inconclusive = unresolvedStatuses.has(result.status);
    const confirmedMAFilingConflict = result.state === 'MA'
      && (result.status_reason === 'MA_FORM_PC_ATTACHMENT_IDENTITY_CONFLICT'
        || result.status_reason === 'MA_FORM_PC_DETAIL_UNCONFIRMED'
          && Number.isInteger(result.ma_filing_evidence?.wrong_filing_year));
    if (!review?.candidates?.length && !inconclusive) return;
    const box = add(parent, 'div', '', 'mt-3 border-t border-slate-200 pt-3 whitespace-normal');
    const message = add(box, 'p', '', 'text-sm text-slate-600'); message.setAttribute('role', 'status');
    const buttons = [];
    if (inconclusive && !review?.candidates?.length) {
      add(box, 'p', maActivityOnly(result) ? 'Filing status unconfirmed' : boundedSourceFailure(result) ? 'Site Not Reachable' : 'Review required', 'font-semibold text-slate-900');
      const fallback = confirmedMAFilingConflict
        ? 'The Massachusetts filing attachment shows a different EIN. Confirm the filing directly with the state.'
        : 'The state lookup did not provide enough confirmed information to establish a status. Review the explanation and available evidence, then retry this state or check its official lookup.';
      add(box, 'p', result.source_note || fallback, 'mt-1 text-xs text-slate-600');
      try {
        const url = new URL(result.source_url);
        if (url.protocol === 'https:' && !url.username && !url.password) {
          const link = add(box, 'a', 'Open state lookup', 'mt-2 block text-xs underline');
          link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        }
      } catch { /* No unverified replacement URL. */ }
    }
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
        if (candidate.group_identity) {
          const group = candidate.group_identity;
          add(card, 'p', `Entered EIN: ${group.requested_ein} · Registry group-return EIN: ${group.registry_ein}`, 'mt-1 text-xs font-semibold');
          add(card, 'p', `IRS metadata shows group exemption ${group.group_exemption_number}. Confirm whether this state's record applies to the entered organization; a group relationship alone does not establish coverage.`, 'mt-1 text-xs text-slate-600');
        }
        add(card, 'p', [candidate.raw_status, candidate.expiration ? `Expiration: ${candidate.expiration}` : ''].filter(Boolean).join(' · '), 'mt-1 text-xs text-slate-600');
        if (candidate.decision !== 'reject' && !(result.success === true && (result.status === 'Not Registered'
          || result.state === 'IL' && result.status === 'Not Registered / Non-Compliant'))) renderEvidence(card, candidate);
        if (candidate.decision) add(card, 'p', candidate.decision === 'accept' ? 'Identity accepted by user' : 'Identity rejected by user', 'mt-2 text-xs font-semibold');
        const controls = add(card, 'div', '', 'mt-2 flex flex-wrap gap-2');
        action(controls, review.exclusive ? 'Confirm this record' : 'Accept match', () => decide(candidate.id, 'accept'), candidate.decision === 'accept').setAttribute('aria-pressed', String(candidate.decision === 'accept'));
        action(controls, 'Reject match', () => decide(candidate.id, 'reject'), candidate.decision === 'reject').setAttribute('aria-pressed', String(candidate.decision === 'reject'));
        if (candidate.decision) action(controls, 'Undo match', () => decide(candidate.id, 'clear'));
      }
    }
    if (inconclusive && !confirmedMAFilingConflict && (!review?.candidates?.some(candidate => candidate.decision)
        || result.state === 'NC' && review.search_complete === false
          && review.candidates.some(candidate => candidate.decision === 'reject'))) {
      const controls = add(box, 'div', '', 'mt-3');
      action(controls, `Retry ${result.state}`, retry);
    }
  }
  function statusLabel(result) {
    if (result.status === 'Closed / Withdrawn / Canceled') return 'Closed / Withdrawn / Canceled / Inactive';
    if (boundedSourceFailure(result)) return result.status;
    if (maActivityOnly(result)) return 'Not Doing Business in Massachusetts';
    const inconclusive = unresolvedStatuses.has(result.status);
    if (inconclusive && result.identity_review?.candidates?.some(candidate => !candidate.decision)) return 'Confirm match';
    return inconclusive ? 'Review required' : result.status || 'Unknown';
  }
  window.CCIdentityReview = Object.freeze({render, renderEvidence, statusLabel, usesSearchHistoryOnly});
})();
