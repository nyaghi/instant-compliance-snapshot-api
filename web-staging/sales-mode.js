(function (root) {
  "use strict";
  // Audited against current master routes, rather than the historical CSV.
  const EIN_STATES = Object.freeze(["AK", "CA", "CO", "HI", "MA", "MD", "MI", "MN", "NJ", "NM", "NY", "OH", "OR", "PA", "VA", "WA"]);
  function isSales(mode) { return mode === "sales-all" || mode === "sales-ein"; }
  function displayStatus(status) {
    if (status === "Upcoming Filing") return "Current";
    if (status === "Not Registered") return "No record found";
    if (["Failed to Renew", "Expired"].includes(status)) return "Delinquent";
    if (status === "Closed / Withdrawn / Canceled") return "Inactive / closed";
    // Exempt, pending, restricted and uncertain results retain their meaning.
    return status || "Unable to Confirm";
  }
  async function runBounded(items, lanes, operation) {
    let cursor = 0;
    const results = new Array(items.length);
    async function worker() {
      while (cursor < items.length) {
        const index = cursor++;
        results[index] = await operation(items[index]);
      }
    }
    await Promise.all(Array.from({length: Math.min(Math.max(1, lanes), items.length)}, worker));
    return results;
  }
  function scopeText(selected, supported, completed) {
    const omitted = supported.filter(state => !selected.includes(state));
    return `${completed} of ${selected.length} selected states completed. ` +
      (omitted.length ? `Not checked: ${omitted.join(", ")}. No registration conclusion is made for those states.` : "All 30 supported states are in scope.");
  }
  const api = Object.freeze({EIN_STATES, isSales, displayStatus, runBounded, scopeText});
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.CCSales = api;
})(typeof window !== "undefined" ? window : globalThis);
