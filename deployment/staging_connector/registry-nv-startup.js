/* Observe the Nevada portal's own configuration requests without changing them. */
(() => {
  'use strict';
  if (window !== window.top || location.origin !== 'https://orion.nv.gov'
      || location.pathname !== '/portal/public/') return;

  const marker = 'data-cc-nv-config-unavailable';
  const open = XMLHttpRequest.prototype.open;
  let failures = 0;
  let responded = false;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    const result = Reflect.apply(open, this, [method, url, ...rest]);
    if (String(method).toUpperCase() !== 'GET') return result;
    try {
      const request = new URL(url, location.href);
      if (request.origin !== 'https://content.orion.nv.gov' || request.pathname !== '/api/tenants')
        return result;
    } catch {
      return result;
    }
    let networkFailed = false;
    const onError = () => { networkFailed = true; };
    this.addEventListener('error', onError, {once: true});
    this.addEventListener('loadend', () => {
      this.removeEventListener('error', onError);
      if (this.status > 0 && this.status < 500) {
        responded = true;
        document.documentElement?.removeAttribute(marker);
      } else if (!responded && (networkFailed || this.status >= 500) && ++failures >= 2) {
        document.documentElement?.setAttribute(marker, '');
      }
    }, {once: true});
    return result;
  };
})();
