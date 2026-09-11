# CharityClarity staging New York connector — 0.1.0

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
- Opens New York's normal search page, clears fields, completes the normal Verify/Search flow, and returns the completed public search response.
- Returns an incomplete result on rejection or failure. It never chooses records or derives a registration status.
- Reads only whitelisted public search-response fields. Cookies, verification tokens, browser history, and login credentials are not sent to CharityClarity.

Compliance Express · www.compliance-express.com · info@compliance-express.com
