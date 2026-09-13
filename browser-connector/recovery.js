/* Fixed registry scope. Cookie values never leave the extension or enter logs. */
(() => {
  "use strict";
  const ORIGIN = "https://charities-search.ag.ny.gov";
  const HOST = "charities-search.ag.ny.gov";
  // This module only operates on the top-level HTTPS registry page. Its
  // schemeful partition site is fixed; asking Chrome for it would require a
  // broader ny.gov host grant, which this extension deliberately does not have.
  const PARTITION = { topLevelSite: "https://ny.gov", hasCrossSiteAncestor: false };
  const key = value => JSON.stringify(value ? [value.topLevelSite || "", !!value.hasCrossSiteAncestor] : null);
  function eligible(cookie, storeId, partition) {
    return cookie.hostOnly === true && cookie.domain === HOST && cookie.storeId === storeId &&
      (!cookie.partitionKey || key(cookie.partitionKey) === key(partition));
  }
  async function clearForTab(tabId, ownedIds, closeOwned) {
    // A customer's already-open NY page may depend on this origin's storage.
    const open = await chrome.tabs.query({ url: ORIGIN + "/*" });
    if (open.some(tab => !ownedIds.includes(tab.id))) throw new Error("NY_CONNECTOR_RECOVERY_PAGE_OPEN");
    const tab = await chrome.tabs.get(tabId);
    if (new URL(tab.url).origin !== ORIGIN) throw new Error("NY_CONNECTOR_RECOVERY_FAILED");
    const stores = await chrome.cookies.getAllCookieStores();
    const store = stores.find(candidate => candidate.tabIds.includes(tabId));
    if (!store) throw new Error("NY_CONNECTOR_RECOVERY_FAILED");
    const partitionKey = PARTITION;
    await closeOwned();
    const before = await chrome.cookies.getAll({ domain: HOST, storeId: store.id, partitionKey: {} });
    let removed = 0;
    for (const cookie of before.filter(item => eligible(item, store.id, partitionKey))) {
      // An expired overwrite addresses the exact host/name/path/store/partition.
      // URL-based remove() can choose a same-name parent cookie instead. Never
      // supply a Domain attribute: shared/domain cookies remain untouched even
      // when another cookie appears between enumeration and this operation.
      await chrome.cookies.set({ url: ORIGIN + "/", name: cookie.name, value: "",
        path: cookie.path, storeId: cookie.storeId, secure: cookie.secure,
        httpOnly: cookie.httpOnly, sameSite: cookie.sameSite, expirationDate: 1,
        ...(cookie.partitionKey ? { partitionKey: cookie.partitionKey } : {}) });
      removed++;
    }
    await chrome.browsingData.remove({ origins: [ORIGIN] }, {
      localStorage: true, indexedDB: true, cacheStorage: true, serviceWorkers: true
    });
    const after = await chrome.cookies.getAll({ domain: HOST, storeId: store.id, partitionKey: {} });
    if (after.some(item => eligible(item, store.id, partitionKey))) throw new Error("NY_CONNECTOR_RECOVERY_FAILED");
    return { scopedCookiesExpired: removed };
  }
  globalThis.CCNYRecovery = Object.freeze({ clearForTab });
})();
