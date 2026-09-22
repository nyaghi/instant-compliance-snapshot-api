# Chrome Web Store submission — 0.4.0

Draft submission material. Not uploaded, reviewed, or published.

## Listing

Name: CharityClarity — New York Connector

Summary: Connect CharityClarity to New York public charity records in your browser.

Description:

Use this companion extension with CharityClarity from Compliance Express to check New York charitable registration records. Start a check in CharityClarity; the connector opens a New York registry tab in the same Chrome window, submits the requested public-record search, and returns the public search evidence to CharityClarity. CharityClarity confirms the record and interprets the registration status.

The connector queues concurrent New York checks, keeps each organization's evidence separate, and closes the registry tabs it created when their checks finish. Keep Chrome open while checks run. New York may require browser verification or temporarily limit requests; the connector reports an incomplete check when the state cannot supply usable evidence.

Authorized CharityClarity access is required. This extension does not provide legal or tax advice and does not establish an organization's authority to solicit. For access or support, contact info@compliance-express.com or visit https://www.compliance-express.com.

## Single purpose

Retrieve public New York charity-search evidence for the organization being checked in CharityClarity.

## Permission justifications

- Approved Compliance Express hosts: connect only the CharityClarity page to the extension; production and staging requests remain bound to their respective backend.
- charities-search.ag.ny.gov: operate the official public search page and read its completed response.
- storage: preserve the in-progress queue across extension-worker restarts and retain bounded recovery timestamps. Session evidence is not retained in permanent extension storage.
- cookies: expire only eligible host-only cookies for the New York search origin during connection recovery. Cookie values are never sent to CharityClarity or included in logs.
- browsingData: clear only New York search-origin local storage, IndexedDB, cache storage, and service workers during recovery. Does not clear browsing history or unrelated sites; protects already-open state tabs.

## Data handling

The extension handles the organization name/EIN, public New York search results, temporary tab/job identifiers, and bounded operational error codes. Public result fields crossing the bridge are limited to registry record ID, organization name, and EIN. Sign-in credentials travel from the CharityClarity webpage to its backend; the extension does not receive them. No advertising, sale of data, or unrelated browsing-history collection is implemented.

Privacy URL after deployment: https://www.compliance-express.com/connector/privacy.html

## Release gates

- Production-domain live smoke and 15-workflow benchmark.
- Publisher dashboard access; confirm publisher registration and required account security.
- Upload the tested ZIP and approved branding/screenshots; complete the actual dashboard's required disclosures accurately.
- Supply a dedicated, restricted reviewer access mechanism if Google requires access. Do not disclose the shared internal administrative passcode to reviewers.
- Google review and approved listing URL.
- Fresh-profile Web Store installation and first-check smoke, including missing-connector guidance, queue behavior, recovery, and uninstall.
- Set the approved Store URL in the production frontend build. Do not substitute an invented listing or a developer-mode ZIP for customer installation.
