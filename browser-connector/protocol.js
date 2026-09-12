/* Public search evidence only. No cookies, credentials, or verification tokens. */
(() => {
  "use strict";
  const STAGING = "https://staging.compliance-express.com";
  const NY = "https://charities-search.ag.ny.gov";
  const FIELDS = ["ein", "orgName", "orgID", "regtype", "city", "state"];
  function validId(value) { return typeof value === "string" && /^[a-zA-Z0-9_-]{16,80}$/.test(value); }
  function validQuery(value) {
    if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== 1) return false;
    if (Object.hasOwn(value, "ein")) return typeof value.ein === "string" && /^[0-9]{9}$/.test(value.ein) && value.ein !== "000000000";
    return Object.hasOwn(value, "orgName") && typeof value.orgName === "string" && value.orgName.trim().length > 0 && value.orgName.length <= 500;
  }
  function sameQuery(actual, expected) {
    return validQuery(expected) && actual && Object.keys(actual).length === 1 &&
      Object.entries(expected).every(([key, value]) => actual[key] === value);
  }
  function publicRequest(raw) {
    let url;
    try { url = new URL(raw, NY); } catch { return null; }
    if (url.origin !== "https://charities-search-api.ag.ny.gov") return null;
    if (url.pathname === "/api/recaptcha/verify") return { kind: "verify" };
    if (url.pathname !== "/api/FileNet/RegistrySearch") return null;
    // Unknown filters or pagination could hide a qualifying record.
    for (const key of url.searchParams.keys()) {
      if (![...FIELDS, "token"].includes(key) || url.searchParams.getAll(key).length !== 1) return null;
    }
    const query = {};
    for (const key of FIELDS) {
      const values = url.searchParams.getAll(key);
      if (values.length > 1) return null;
      if (values[0]) query[key] = key === "ein" && /^[0-9]{2}-?[0-9]{7}$/.test(values[0]) ? values[0].replace("-", "") : values[0];
    }
    return { kind: "search", query };
  }
  function publicResponse(request, status, payload) {
    if (request.kind === "verify") return { kind: "verify", http_status: status, verified: payload?.verified === true };
    const rows = payload?.data;
    if (status !== 200) throw new Error("NY_CONNECTOR_SEARCH_HTTP_ERROR");
    if (payload?.success !== true || payload?.statusCode !== 200) throw new Error("NY_CONNECTOR_SEARCH_UNSUCCESSFUL");
    if (!Array.isArray(rows) || rows.length > 1000) throw new Error("NY_CONNECTOR_SEARCH_ROWS_INVALID");
    return { kind: "search", query: request.query, http_status: status,
      success: payload?.success === true, statusCode: payload?.statusCode,
      rows: rows.map(row => {
        if (!row || typeof row.orgID !== "string" || !/^[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(row.orgID) ||
          typeof row.orgName !== "string" || !row.orgName.trim() || row.orgName.length > 500) throw new Error("NY_CONNECTOR_SEARCH_IDENTITY_INVALID");
        if (!Object.hasOwn(row, "ein")) throw new Error("NY_CONNECTOR_SEARCH_EIN_MISSING");
        if (row.ein === null) throw new Error("NY_CONNECTOR_SEARCH_EIN_NULL");
        if (typeof row.ein !== "string") throw new Error("NY_CONNECTOR_SEARCH_EIN_TYPE");
        if (row.ein && !/^[0-9]{2}-?[0-9]{7}$/.test(row.ein)) throw new Error("NY_CONNECTOR_SEARCH_EIN_FORMAT");
        return { orgID: row.orgID, orgName: row.orgName, ein: row.ein };
      }) };
  }
  globalThis.CCNYProtocol = Object.freeze({ STAGING, NY, validId, validQuery, sameQuery, publicRequest, publicResponse });
})();
