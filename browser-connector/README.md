# CharityClarity staging New York connector — 0.2.1

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
- Keeps that tab in the window containing the originating staging tab. A queued tab moved to another window is resolved when its turn starts. The connector does not focus a Chrome window; a dedicated validation window can operate separately from the user's work.
- Staging sessions in the same Chrome profile enter a FIFO queue. A queued request may wait up to twenty minutes; the active lookup then has its own five-minute limit. The master starts its signed evidence continuation only after admission. Other states continue while New York waits. This is a per-browser queue, not a platform-wide concurrency limit.
- The connector waits at least three seconds between organization lookups. Completion, error, expiry, or disconnection closes only its owned tab before the next lookup starts. Closing a waiting session removes it from the queue. A browser/worker crash fails conservatively; an orphan tab is never reused as evidence.
- Verification/search network errors are reported immediately. HTTP 401 rejection at Verify or Search gets at most one recovery attempt per organization lookup, shared across both steps and EIN/name fallback. A rejected Search clears the form and repeats its normal Verify/Search flow once. HTTP 429 gets at most two retries, after five and fifteen seconds, shared across the lookup. Other errors are not retried. Verification is never bypassed; tokens are neither retained nor reused by the connector.
- Returns an incomplete result on rejection or failure. It never chooses records or derives a registration status.
- Reads only whitelisted public search-response fields. Cookies, verification tokens, browser history, and login credentials are not sent to CharityClarity.

Compliance Express · www.compliance-express.com · info@compliance-express.com
