# CharityClarity staging New York connector — 0.1.4

This internal prototype is restricted to staging.compliance-express.com and the New York charities registry. It is not published to the Chrome Web Store and has not been approved for production.

## Install for testing

1. Keep this folder on your computer.
2. In your regular Chrome profile, open `chrome://extensions`.
3. Turn on **Developer mode**, select **Load unpacked**, and choose this folder (the one containing `manifest.json`).
4. Refresh CharityClarity staging. After unlocking staging, the New York connector panel should show **ready** when the prototype frontend is deployed.

Only install this reviewed folder. No Google login, cookie transfer, API key, or CharityClarity passcode goes into the extension. The extension opens and closes a NY search tab; all record matching and compliance interpretation stay in CharityClarity's backend. Keep Chrome open during checks.

The prototype has no automatic update service. If a test fix is made, reload it on Chrome's Extensions page and refresh the staging page. Remove it there when testing is over.

## What it does

- Receives a single EIN or name query from the staging page, after the backend chooses the query.
- Opens one New York search tab per organization lookup, retains it for the master's EIN-to-name fallback, clears fields before each query, and completes the normal Verify/Search flow. It returns only completed public search responses.
- A staging-tab-bound connection keeps the worker available for at most five minutes (Chrome 114+). Completion, error, expiry, or disconnection closes the connector-owned tab. User-opened registry tabs are not used or closed. A browser/worker crash fails conservatively; an orphan tab is never reused as evidence.
- Verification/search network errors are reported immediately. HTTP 401 rejection at Verify or Search gets at most one recovery attempt per organization lookup, shared across both steps and EIN/name fallback. A rejected Search clears the form and repeats its normal Verify/Search flow once. Other errors are not retried. Verification is never bypassed; tokens are neither retained nor reused by the connector.
- Returns an incomplete result on rejection or failure. It never chooses records or derives a registration status.
- Reads only whitelisted public search-response fields. Cookies, verification tokens, browser history, and login credentials are not sent to CharityClarity.

Compliance Express · www.compliance-express.com · info@compliance-express.com
