# New York browser connector — staging prototype

Authorized September 11, 2026: the user explicitly approved a staging-only browser connector prototype after reviewing the regular-browser versus automated local/cloud results. This authorizes the transport exception in root AGENTS.md; no production rollout is authorized.

The extension performs NY UI interaction and captures only completed public search responses. It does not choose records, determine fallback names, interpret filings, or classify registration status. Those decisions remain in registry_snapshot_server.py through the existing search_ny_direct interpreter. Positive detail responses are fetched independently from the official service by the backend.

The staging-only /api/ny-connector endpoint requires the existing internal staging authentication and exact staging Origin on every request. Its random, short-lived check token is bound to organization, email, and browser identifier. Each pending query has a one-use nonce. A response must contain the exact issued query and complete public rows. Failed verification, missing/closed browser, stale/malformed responses and timeouts remain inconclusive.

Prototype sessions are in memory for at most five minutes. A restart or an instance change ends an unfinished session safely; the user must rerun it. This prototype is not a distributed browser-job service. The 16-session cap protects only this prototype's temporary records and does not implement the deferred platform-wide 15-workflow concurrency feature.

The connector works only on staging.compliance-express.com and charities-search.ag.ny.gov. It requests no cookies, debugger, browsing-history, storage, or arbitrary scripting permissions. It observes NY's existing XMLHttpRequest/fetch response bodies while the normal Verify/Search buttons are used; it never extracts or reuses verification tokens. Public response metadata is whitelisted before crossing the browser boundary.

Installation is an unpacked Chrome extension for internal staging validation; no Chrome Web Store publication is included. web-staging/connector/index.html provides the package and installation steps. If NY verification rejects this extension's actual interaction model, stop and report that limitation rather than altering fingerprints or disguising automation.

Prototype deployment gates: backend and browser contract tests; existing 26 suites and NY retrieval tests; fixture current/exempt/no-record controls; live mature-state control; mixed-state batch isolation; source and package audit. The approved staging prototype must be deployed before its installed extension can be tested through the real staging frontend and backend. Staging deployment alone is not proof that New York accepts the connector.

After prototype deployment, verify the live staging assets and both backends, then run actual installed-extension searches and independently verified backend results for current/exempt/no-record controls. Preserve the previous 265-control evidence as baseline and document which source hash each later test covered. First-40 post-validation may start only after those live integration and staging smoke gates pass, and must stop on the first mismatch/error/missing approved expectation. The earlier headless NY failure remains recorded; it is not relabeled as a pass.

Installation constraint: on September 11 the user explicitly asked the agent to install the connector. Browser Use rejected opening chrome://extensions under its URL security policy and explicitly prohibited alternate installation routes. The user was asked to load this reviewed folder manually. No installation bypass was attempted.
