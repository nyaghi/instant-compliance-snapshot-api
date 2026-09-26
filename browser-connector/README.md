# CharityClarity registry connector — 0.5.3 candidate

This candidate adds Illinois and Georgia on staging only. New York retains its existing workflow. This package has passed local protocol, queue and backend tests; live IL/GA connector validation remains required before release.

- Illinois: EIN-first search, selected detail EIN confirmation, full result pagination, state annual-report deadline.
- Georgia: normal charity-search form, reviewed names, complete pagination and primary charity-license details. Associated paid solicitors are not alternate names.
- The master backend owns all matching and status decisions. The browser returns public evidence only.
- No verification cookies, CAPTCHA tokens, credentials or hidden form state are forwarded.
- Incomplete or blocked searches stay inconclusive. Only completed Illinois searches can receive the new combined status.

## Update for live validation

1. Open Chrome's Extensions page yourself (`chrome://extensions`).
2. If updating an existing unpacked connector, use this candidate folder as its source, or disable the old connector and choose **Load unpacked** with this folder. Keep only one CharityClarity connector enabled.
3. Verify version **0.5.3**. Refresh the staging tab.
4. Keep Chrome open. Illinois and Georgia require the corresponding staging frontend/backend candidate before end-to-end checks can run.

The additional host permissions are limited to the official Illinois and Georgia public registries. Production web/backend deployments are not part of this package.

---

## Existing New York workflow reference

# CharityClarity staging New York connector — 0.3.6

This internal prototype is restricted to staging.compliance-express.com and the New York charities registry. It is not published to the Chrome Web Store and has not been approved for production.

## Install for testing

1. Keep this folder on your computer.
2. In your regular Chrome profile, open `chrome://extensions`.
3. Turn on **Developer mode**, select **Load unpacked**, and choose this folder (the one containing `manifest.json`).
4. Refresh CharityClarity staging. After unlocking staging, the panel should say **New York connector connected**. Chrome 132 or later is required; review the additional connection-refresh permissions if Chrome requests them.

Only install this reviewed folder. No Google login, cookie transfer, API key, or CharityClarity passcode goes into the extension. The extension opens and closes a NY search tab; all record matching and compliance interpretation stay in CharityClarity's backend. Keep Chrome open during checks.

The prototype has no automatic update service. If a test fix is made, reload it on Chrome's Extensions page and refresh the staging page. Remove it there when testing is over.

## What it does

- Receives a single EIN or name query from the staging page, after the backend chooses the query.
- Opens an inactive New York search tab per organization lookup, retains it for the master's EIN-to-name fallback, clears fields before each query, and completes the normal Verify/Search flow. A connection repair replaces that owned tab once. It returns only completed public search responses and the selected record’s public identity and filing dates. The master issues the record ID; the connector clicks that exact result link in the same verified tab. Same-EIN duplicates use browser Back to compare the next master-selected record. It does not read or forward verification tokens.
- Keeps that tab in the window containing the originating staging tab. A queued tab moved to another window is resolved when its turn starts. The connector does not focus a Chrome window; a dedicated validation window can operate separately from the user's work.
- Staging sessions in the same Chrome profile enter a FIFO queue. A queued request may wait up to twenty minutes; the active lookup then has its own five-minute limit. The master starts its signed evidence continuation only after admission. Other states continue while New York waits. This is a per-browser queue, not a platform-wide concurrency limit.
- The connector waits at least three seconds between organization lookups. Completion, error, or expiry closes only its owned tab before the next lookup starts. Closing a waiting session removes it from the queue. Temporary transport loss reconnects to the same job; worker restarts restore its queue position, original deadline, owned tab, and consumed retry budgets. A bounded worker heartbeat operates only while checks are pending. A full browser close or extension reload can still interrupt checks.
- Verification/search network errors are reported immediately. The existing normal Verify/Search retry remains shared across both steps and EIN/name fallback. If HTTP 401 persists, one coordinated connection repair may create a fresh page and retry the same master-issued query. A failed repair stops queued NY checks conservatively; it does not reset the connection separately for each organization. The shared repair allowance is persisted across worker restarts and limited to once per twenty minutes, an operational bound rather than a promise that the state will accept verification then. HTTP 429 retains its two bounded retries.
- **Refresh New York connection** uses the same coordinated operation and allowance. Successful manual refresh retries only an existing inconclusive NY result for the same organization on that page. Other state results and their original report timestamp remain unchanged. A reconnect resends the same command ID and query. The page relay joins an existing request or returns its completed public response, avoiding duplicate searches. The signed master check is never resumed with an unrelated response. Recovery attempts and original deadlines stay bounded; an interrupted connection-cleanup operation still fails safely and retains its cooldown.
- Connection cleanup uses exact host-only cookie expiration and origin-filtered local storage, IndexedDB, Cache Storage and service-worker removal for `https://charities-search.ag.ny.gov`. It does not clear browsing history, shared/domain cookies, unrelated sites or third-party verification storage. An open user-owned NY page blocks cleanup. Local persistence contains only repair timing and reason; owned-tab/queue metadata, current public query/response, and bounded connection diagnostics use restricted extension session storage. No sign-in credentials or verification tokens enter this journal. Extension reload/update can interrupt work and must be done between checks.
- Returns an incomplete result on rejection or failure. It never chooses records or derives a registration status.
- Search responses have a thirty-second wait. A missing response shares the existing single timeout retry with page-load and verification timeouts, using a new owned tab and the same query. This does not reset the overall lookup deadline or verification-rejection allowance.
- Reads only whitelisted public search and detail-response fields. Cookies, verification tokens, browser history, and login credentials are not sent to CharityClarity.

Compliance Express · www.compliance-express.com · info@compliance-express.com

Georgia pagination activates the existing public pager link in page context. No new permissions or state API access are added.

Version 0.5.3 validates both public Georgia result layouts (combined address or split city/state). Unknown layouts and malformed rows remain incomplete evidence rather than completed empty searches. No new permissions or matching/status rules.
