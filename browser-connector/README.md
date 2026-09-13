# CharityClarity staging New York connector — 0.3.1

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
- Opens an inactive New York search tab per organization lookup, retains it for the master's EIN-to-name fallback, clears fields before each query, and completes the normal Verify/Search flow. A connection repair replaces that owned tab once. It returns only completed public search responses.
- Keeps that tab in the window containing the originating staging tab. A queued tab moved to another window is resolved when its turn starts. The connector does not focus a Chrome window; a dedicated validation window can operate separately from the user's work.
- Staging sessions in the same Chrome profile enter a FIFO queue. A queued request may wait up to twenty minutes; the active lookup then has its own five-minute limit. The master starts its signed evidence continuation only after admission. Other states continue while New York waits. This is a per-browser queue, not a platform-wide concurrency limit.
- The connector waits at least three seconds between organization lookups. Completion, error, expiry, or disconnection closes only its owned tab before the next lookup starts. Closing a waiting session removes it from the queue. A browser/worker crash fails conservatively; an orphan tab is never reused as evidence.
- Verification/search network errors are reported immediately. The existing normal Verify/Search retry remains shared across both steps and EIN/name fallback. If HTTP 401 persists, one coordinated connection repair may create a fresh page and retry the same master-issued query. A failed repair stops queued NY checks conservatively; it does not reset the connection separately for each organization. The shared repair allowance is persisted across worker restarts and limited to once per twenty minutes, an operational bound rather than a promise that the state will accept verification then. HTTP 429 retains its two bounded retries.
- **Refresh New York connection** uses the same coordinated operation and allowance. Successful manual refresh retries only an existing inconclusive NY result for the same organization on that page. Other state results and their original report timestamp remain unchanged. Pending checks interrupted by a worker crash fail explicitly; they are not silently replayed with uncertain evidence. The signed master check is never resumed with an unrelated response.
- Connection cleanup uses exact host-only cookie expiration and origin-filtered local storage, IndexedDB, Cache Storage and service-worker removal for `https://charities-search.ag.ny.gov`. It does not clear browsing history, shared/domain cookies, unrelated sites or third-party verification storage. An open user-owned NY page blocks cleanup. Local persistence contains only repair timing and reason; owned-tab/queue metadata uses restricted extension session storage. Extension reload/update can interrupt work and must be done between checks.
- Returns an incomplete result on rejection or failure. It never chooses records or derives a registration status.
- Reads only whitelisted public search-response fields. Cookies, verification tokens, browser history, and login credentials are not sent to CharityClarity.

Compliance Express · www.compliance-express.com · info@compliance-express.com
