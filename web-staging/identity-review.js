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
      && (result.success === false && !result.confirmation_required
          && result.source_availability?.schema === 1
          && ['source_error', 'transport_error', 'deadline_exhausted', 'rate_limited'].includes(result.source_availability.kind)
        || result.state === 'OR' && ['OR_SOURCE_UNREACHABLE', 'OR_SOURCE_ACCESS_REFUSED', 'OR_SOURCE_TIME_LIMIT'].includes(result.reason_code)
        || result.state === 'NM' && result.status_reason === 'NY_CONNECTOR_REGISTRY_NM_HTTP_ERROR'
        || result.state === 'NV' && ['NY_CONNECTOR_REGISTRY_NV_STARTUP_UNREACHABLE','NY_CONNECTOR_REGISTRY_NV_FORM_LOAD_TIMEOUT','NY_CONNECTOR_REGISTRY_NV_SEARCH_RESPONSE_TIMEOUT','NY_CONNECTOR_REGISTRY_NV_LOOKUP_TIMEOUT','NY_CONNECTOR_REGISTRY_NV_SEARCH_SOURCE_ERROR'].includes(result.status_reason)
        || result.state === 'DC' && result.reason_code === 'DC_LICENSE_SOURCE_UNREACHABLE'
        || result.state === 'MD' && result.success === false
           && result.raw_status_text === 'Maryland registry search did not complete'
           && ['PORTAL_ERROR', 'RUNNER_TIMEOUT'].includes(result.reason_code)
        || result.state === 'CT' && result.success === false
           && result.raw_status_text === 'Connecticut direct registry lookup could not be completed'
           && ['PORTAL_ERROR', 'RUNNER_TIMEOUT'].includes(result.reason_code)
        || result.state === 'OK' && result.success === false && !result.confirmation_required
           && result.reason_code === 'PORTAL_ERROR' && result.error === 'Could not select Oklahoma Search by Name.'
        || result.state === 'WI' && ['WI_SOURCE_UNREACHABLE', 'WI_SOURCE_ALLOWANCE_EXHAUSTED'].includes(result.reason_code)
        || result.state === 'MS' && result.status_reason === 'NY_CONNECTOR_REGISTRY_MS_HOST_ERROR'
        || result.state === 'FL' && ['FL_INCOMPLETE_SEARCH','FL_SOURCE_NOT_RESPONDING'].includes(result.reason_code)
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
  function usesIncompleteSearchHistory(result) {
    return result.success === false && (
      result.state === 'AR' && result.status_reason === 'AR_REQUIRED_SEARCH_INCOMPLETE'
      || result.state === 'NC' && result.status_reason === 'NY_CONNECTOR_NC_RATE_LIMITED'
      || result.state === 'TN' && [
        'NY_CONNECTOR_TN_OPTIONAL_CAPTURE_CLEANUP_TIMEOUT',
        'NY_CONNECTOR_TN_SEARCH_DELIVERY_TIMEOUT',
        'NY_CONNECTOR_REGISTRY_TN_RESPONSE_PENDING',
        'NY_CONNECTOR_REGISTRY_TN_PAGINATION_INCOMPLETE',
      ].includes(result.status_reason));
  }
  function renderEvidence(parent, result) {
    const source = /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(result.evidence_url || '');
    const bundle = /^\/state-evidence\/([a-f0-9]{64})\/evidence\.zip$/.exec(result.evidence_bundle_url || '');
    const history = /^\/state-evidence\/([a-f0-9]{64})\/search-history\.pdf$/.exec(result.search_history_url || '');
    const validHistory = history && (!result.evidence_bundle_url || bundle && bundle[1] === history[1]);
    const incompleteAttempts = usesIncompleteSearchHistory(result);
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
      add(box, 'p', maActivityOnly(result) ? 'Filing status unconfirmed' : statusLabel(result), 'font-semibold text-slate-900');
      const fallback = confirmedMAFilingConflict
        ? 'The Massachusetts filing attachment shows a different EIN. Confirm the filing directly with the state.'
        : 'The state lookup did not provide enough confirmed information to establish a status. Review the explanation and available evidence, then retry this state or check its official lookup.';
      if (statusLabel(result) !== 'Review required') add(box, 'p', result.source_note || fallback, 'mt-1 text-xs text-slate-600');
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
    if (inconclusive && result.state === 'RI') {
      return result.status_reason === 'RI_LOOKUP_TIMEOUT' || result.reason_code === 'RUNNER_TIMEOUT'
        ? 'Search timed out' : 'Registry check incomplete';
    }
    return inconclusive ? 'Review required' : result.status || 'Unknown';
  }
  function reviewHandoff(result) {
    if (statusLabel(result) !== 'Review required') return '';
    const genericNote = text => !text || /^(?:The registry check did not provide enough information|The registry search or selected record did not return complete|No explanation accompanied)/i.test(text);
    const notes = [result.source_note, result.comments].map(value => String(value || '').trim());
    const note = notes.find(text => !genericNote(text)) || notes.find(Boolean) || '';
    const diagnostic = result.lab_diagnostic || {};
    const codes = [result.status_reason, result.reason_code, diagnostic.code].filter(Boolean).join(' ');
    let reason = '';
    let action = '';
    if (result.state === 'NV' && /charitable solicitation registration or exemption|Review the entity's filing scope/i.test(note)) {
      action = 'Check Nevada filing history for a charitable solicitation registration or exemption under the legal name shown above. Compare the filing year and organization before assigning a status.';
    } else if (/EIN_CONFLICT|TAX_ID_CONFLICT|ATTACHMENT_IDENTITY_CONFLICT/.test(codes)) {
      reason = 'The tax ID on the state record or filing conflicts with the entered EIN.';
      action = 'Compare the EIN on the state filing with the entered EIN. Use a filing belonging to the entered organization before assigning its status.';
    } else if (/FILING_PERIOD_UNVERIFIED|FILING_DATE_UNCONFIRMED|PC_DETAIL_UNCONFIRMED/.test(codes)) {
      reason = 'Aurora could not verify a filing period for the matched organization.';
      action = 'Open the filing history for the matched record and check the most recent filing for this EIN and fiscal period.';
    } else if (/CONNECTOR_(?:UNAVAILABLE|UPDATE_REQUIRED|INTERRUPTED)/.test(codes)) {
      reason = 'Aurora lost the browser connector or could not start it for this check.';
      action = 'Restore the registry connector connection in Aurora, then retry this state.';
    } else if (/VERIFICATION_PENDING|VERIFICATION_REQUIRED|RATE_LIMIT|TIMEOUT|TIMED_OUT/.test(codes)) {
      reason = /RATE_LIMIT/.test(codes) ? 'The registry limited further requests.' :
        /VERIFICATION/.test(codes) ? 'The registry verification step did not finish.' : 'The state check exceeded its time limit.';
      action = 'Retry this state. If the check still stalls, use the official registry to verify the organization and its latest status.';
    } else if (/CARD_CHANGED|DETAIL_UNAVAILABLE|RESULT_LIMIT|SEARCH_INCOMPLETE|INVALID_SEQUENCE|RESPONSE_PENDING/.test(codes)) {
      reason = /CARD_CHANGED|DETAIL_UNAVAILABLE/.test(codes) ? 'Aurora could not read the required details from the state record.' :
        /RESULT_LIMIT/.test(codes) ? 'The registry limited the results returned for this search.' : 'The registry search stopped before Aurora could confirm the result.';
      action = 'Check the relevant record in the state registry and verify its current registration. You can also retry this state.';
    } else if (/identity|different (?:organization|EIN)|multiple (?:records|matches)|unique safe match/i.test(note)) {
      action = 'Compare the state records with the entered legal name and EIN. If the registry omits the EIN, check the registered address or an original filing.';
    } else {
      action = 'Check the latest registration or filing for this organization in the state registry. If the result is still unclear, confirm it with the registry.';
    }
    const raw = String(result.raw_status_text || '').trim();
    const recordedFailure = /failed|incomplete|conflict|could not|timed out|unavailable|missing/i.test(raw) ? raw : '';
    const description = genericNote(note) ? reason || recordedFailure || note || 'The check ended without a confirmed registry status or a recorded cause.' : note;
    const locator = [result.matched_registry_name, result.matched_registry_identifier].filter(Boolean).join(' · ');
    const entered = [result.organization_name, result.ein && 'EIN ' + result.ein].filter(Boolean).join(' · ');
    const anchor = locator ? 'Registry record: ' + locator : entered ? 'Organization checked: ' + entered : '';
    const pending = diagnostic.pending_identifier;
    const inProgress = pending && !description.includes(pending) && pending !== result.matched_registry_identifier
      ? 'Record being checked when the lookup stopped: ' + pending : '';
    const evidence = /^\/state-snapshots\/[a-f0-9]{64}\.pdf$/.test(result.evidence_url || '')
      ? 'Start with the linked state snapshot.' : usesIncompleteSearchHistory(result) && result.search_history_url
        ? 'Start with the recorded search terms.' : '';
    return [description, anchor, inProgress, 'Next step: ' + [evidence, action].filter(Boolean).join(' ')].filter(Boolean).join('\n');
  }
  window.CCIdentityReview = Object.freeze({render, renderEvidence, statusLabel, reviewHandoff, usesSearchHistoryOnly, usesIncompleteSearchHistory});
})();
