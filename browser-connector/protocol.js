/* Public search evidence only. No cookies, credentials, or verification tokens. */
(() => {
  "use strict";
  const STAGING = "https://staging.compliance-express.com";
  const APP_ORIGINS = Object.freeze([STAGING, "https://www.compliance-express.com", "https://compliance-express.com"]);
  function allowedOrigin(origin) { return APP_ORIGINS.includes(origin); }
  const NY = "https://charities-search.ag.ny.gov";
  const FIELDS = ["ein", "orgName", "orgID", "regtype", "city", "state"];
  function validId(value) { return typeof value === "string" && /^[a-zA-Z0-9_-]{16,80}$/.test(value); }
  function validQuery(value) {
    if (value?.state === "IL" || value?.state === "GA") {
      const keys = Object.keys(value).sort().join(",");
      if (keys === "ein,state") return value.state === "IL" && typeof value.ein === "string" && /^[0-9]{9}$/.test(value.ein) && value.ein !== "000000000";
      if (keys === "orgName,state") return typeof value.orgName === "string" && value.orgName.trim().length > 0 && value.orgName.length <= 500;
      if (keys === "identifier,state") return value.state === "IL" && /^\d{8}$/.test(value.identifier);
      return keys === "detail_key,identifier,state" && value.state === "GA" && /^CH\d+$/.test(value.identifier) && /^[a-f0-9-]{36}$/.test(value.detail_key);
    }
    if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== 1) return false;
    if (Object.hasOwn(value, "ein")) return typeof value.ein === "string" && /^[0-9]{9}$/.test(value.ein) && value.ein !== "000000000";
    if (Object.hasOwn(value, "orgID")) return typeof value.orgID === "string" && /^[0-9]{2}-[0-9]{2}-[0-9]{2}$/.test(value.orgID);
    return Object.hasOwn(value, "orgName") && typeof value.orgName === "string" && value.orgName.trim().length > 0 && value.orgName.length <= 500;
  }
  function sameQuery(actual, expected) {
    return validQuery(expected) && actual && Object.keys(actual).length === Object.keys(expected).length &&
      Object.entries(expected).every(([key, value]) => actual[key] === value);
  }
  function publicRequest(raw) {
    let url;
    try { url = new URL(raw, NY); } catch { return null; }
    if (url.origin !== "https://charities-search-api.ag.ny.gov") return null;
    if (url.pathname === "/api/recaptcha/verify") return { kind: "verify" };
    if (url.pathname === "/api/FileNet/RegistryDetail") {
      if ([...url.searchParams.keys()].some(key => !["orgID", "token"].includes(key) || url.searchParams.getAll(key).length !== 1)) return null;
      const query = { orgID: url.searchParams.get("orgID") };
      return validQuery(query) ? { kind: "detail", query } : null;
    }
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
    if (request.kind === "detail") {
      const data = payload?.data;
      const exempt = [data?.regType, data?.regStatute].some(value => typeof value === "string" && value.trim().toUpperCase() === "EXEMPT");
      if (status !== 200 || payload?.success !== true || payload?.statusCode !== 200 || !data || Array.isArray(data) ||
          data.orgID !== request.query.orgID || typeof data.orgName !== "string" || !data.orgName.trim() || data.orgName.length > 500 ||
          !Object.hasOwn(data, "ein") || (data.ein !== null && typeof data.ein !== "string") ||
          (data.ein && !/^[0-9]{2}-?[0-9]{7}$/.test(data.ein)) ||
          (!(exempt && data.documents === undefined) && (!data.documents || typeof data.documents !== "object" || Array.isArray(data.documents) || Object.keys(data.documents).length > 20))) throw new Error("NY_CONNECTOR_DETAIL_INCOMPLETE");
      const detail = {};
      for (const key of ["orgID", "orgName", "ein", "regType", "regStatute", "address", "city", "state", "zip", "status", "registrationStatus", "orgStatus"]) {
        if (!Object.hasOwn(data, key)) continue;
        if (data[key] !== null && (typeof data[key] !== "string" || data[key].length > 1000)) throw new Error("NY_CONNECTOR_DETAIL_INCOMPLETE");
        detail[key] = key === "ein" && data[key] === null ? "" : data[key];
      }
      if (exempt && data.documents === undefined) return { kind: "detail", query: request.query, http_status: status, success: true, statusCode: 200, detail };
      detail.documents = Object.create(null); let count = 0;
      for (const [category, entries] of Object.entries(data.documents)) {
        if (category.length > 200 || !Array.isArray(entries) || (count += entries.length) > 1000) throw new Error("NY_CONNECTOR_DETAIL_INCOMPLETE");
        detail.documents[category] = entries.map(entry => {
          if (!entry || typeof entry !== "object" || Array.isArray(entry)) throw new Error("NY_CONNECTOR_DETAIL_INCOMPLETE");
          const dates = {};
          for (const key of ["fiscalYearEnd", "received"]) if (Object.hasOwn(entry, key)) {
            if (entry[key] !== null && (typeof entry[key] !== "string" || entry[key].length > 100)) throw new Error("NY_CONNECTOR_DETAIL_INCOMPLETE");
            dates[key] = entry[key];
          }
          return dates;
        });
      }
      return { kind: "detail", query: request.query, http_status: status, success: true, statusCode: 200, detail };
    }
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
        // NY uses null in some search rows but an empty string in the detail.
        // Preserve the row; the master still confirms its name and detail ID.
        const ein = row.ein === null ? "" : row.ein;
        if (typeof ein !== "string") throw new Error("NY_CONNECTOR_SEARCH_EIN_TYPE");
        if (ein && !/^[0-9]{2}-?[0-9]{7}$/.test(ein)) throw new Error("NY_CONNECTOR_SEARCH_EIN_FORMAT");
        return { orgID: row.orgID, orgName: row.orgName, ein };
      }) };
  }
  globalThis.CCNYProtocol = Object.freeze({ STAGING, APP_ORIGINS, allowedOrigin, NY, validId, validQuery, sameQuery, publicRequest, publicResponse });
})();
