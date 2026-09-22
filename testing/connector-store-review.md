# Store review access

The submission review page is a test client for the unchanged 0.4.0 extension. It sends the existing ping/acquire/search/finish and recovery commands and displays the sanitized live public evidence. It deliberately has no backend client, compliance classification, customer data, account access, or embedded credentials. There is no new runtime state checker or alternate interpretation rule; the master backend continues to own matching and classification in CharityClarity.

Technical reason: Google must be able to test the extension's core retrieval functionality without receiving the shared internal account passcode or adding a new authorization exception to production. The review page is public, noindexed and transparently labeled. It does not conceal features from Google or return simulated records. The full website's protected access remains unchanged.

Build review-protocol.js from the exact packaged browser-connector/protocol.js. Do not modify the submitted extension ZIP or its runtime for this page. Store instructions should state that no credentials are required on the review page and that full-platform account access is separate.
