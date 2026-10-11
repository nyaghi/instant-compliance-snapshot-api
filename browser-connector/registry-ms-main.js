/* Observe the public Mississippi search request; never submit or alter it. */
(() => {
  'use strict';
  const origin = 'https://charities.sos.ms.gov';
  const path = '/online/portal/ch/page/charities-search/Portal.aspx';
  const channel = 'cc-final-four-ms-search-v1';
  if (window !== window.top || location.origin !== origin || location.pathname !== path) return;

  let active = null;
  const requests = new WeakMap();
  const send = (kind, transaction, extra = {}) => window.postMessage(
    {channel, kind, id: transaction.id, ...extra}, origin);
  const searchRequest = (method, requestUrl, data) => {
    try {
      const url = new URL(requestUrl, location.href);
      if (url.origin !== origin || !/\/Services\/Common\/IFSServices\.asmx\/ExecuteSearch$/i.test(url.pathname)
          || String(method).toUpperCase() !== 'POST' || typeof data !== 'string') return null;
      const body = JSON.parse(data);
      return typeof body.entityName === 'string' && !body.fileNumber ? body.entityName : null;
    } catch (_) { return null; }
  };
  // The public page loads more than one jQuery bundle; a prefilter attached
  // to one instance can miss later searches. Observe the native XHR used by
  // either instance; pass every request and response to the page unchanged.
  const open = XMLHttpRequest.prototype.open;
  const transmit = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...args) {
    requests.set(this, {method, url});
    return open.call(this, method, url, ...args);
  };
  XMLHttpRequest.prototype.send = function(data) {
    const request = requests.get(this);
    const transaction = active;
    if (transaction && Date.now() <= transaction.expires && !transaction.xhr
        && searchRequest(request?.method, request?.url, data) === transaction.name) {
      transaction.xhr = this;
      send('started', transaction);
      this.addEventListener('loadend', () => {
        if (active !== transaction || Date.now() > transaction.expires) return;
        let responseShape;
        try {
          if (this.status !== 200) throw Error('http error');
          const payload = JSON.parse(JSON.parse(this.responseText).d);
          if (payload && typeof payload === 'object') {
            const keys = Object.keys(payload).filter(key => /^[A-Za-z0-9_-]{1,32}$/.test(key)).slice(0, 10);
            responseShape = {kind: Array.isArray(payload) ? 'array' : 'object', keys};
          } else {
            responseShape = {kind: payload === null ? 'null' : typeof payload,
              length: typeof payload === 'string' ? payload.length : undefined};
          }
          // A completed no-match ExecuteSearch response uses an empty string.
          // The visible no-match grid must still agree before classification.
          let table;
          if (payload === '') table = [];
          else {
            if (!payload || !Object.prototype.hasOwnProperty.call(payload, 'Table'))
              throw Error('missing table');
            table = payload.Table === null ? [] : payload.Table;
          }
          if (!Array.isArray(table) || table.length > 100) throw Error('invalid table');
          const identifiers = table.map(row => String(row.FilingFileNumber || ''));
          if (identifiers.some(value => !/^\d{5,15}$/.test(value))) throw Error('invalid row');
          send('success', transaction, {identifiers});
        } catch (error) {
          const reason = this.status !== 200 ? 'http'
            : ['missing table', 'invalid table', 'invalid row'].includes(error?.message)
              ? error.message.replaceAll(' ', '-') : 'invalid-json';
          send('error', transaction, {reason, shape: reason === 'missing-table' ? responseShape : undefined});
        }
        active = null;
      }, {once:true});
    }
    return transmit.call(this, data);
  };
  window.addEventListener('message', event => {
    const message = event.data;
    if (event.source !== window || event.origin !== origin || message?.channel !== channel
        || message.kind !== 'arm' || typeof message.id !== 'string'
        || !/^[a-f0-9-]{36}$/.test(message.id) || typeof message.name !== 'string'
        || !message.name.trim() || message.name.length > 200) return;
    active = {id: message.id, name: message.name, xhr: null, expires: Date.now() + 35000};
    send('armed', active);
  });
})();
