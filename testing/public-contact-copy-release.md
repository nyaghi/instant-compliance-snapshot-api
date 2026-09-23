# CharityClarity public website cleanup

Public promotional entry points now direct visitors to info@compliance-express.com for CharityClarity information. Removed the obsolete Try/Open/free-check invitations. The actual authorized check controls and direct production tool URL remain available.

- Audited 319 published HTML, JavaScript, JSON and XML files against source hashes; none missing.
- Final contact cleanup: 192 pages, 388 public links changed to contact. The earlier wording correction is incorporated.
- Preserved 139 unrelated published assets, both existing Netlify functions, all backend deployments, credentials, access rules and the Chrome Store reviewer page.
- Production app remains 2026.09.20.6, with no Sales mode. No staging deployment performed.
- Preview and production: 192/192 changed pages returned HTTP 200 and passed copy/link checks.
- The generated production app exactly matches the deployed app. Executable scripts are identical to the previously verified copy cleanup; only display strings changed in that earlier step. Inline JavaScript parses successfully.
- Canonical marketing source: 190 files updated only after matching known source hashes. The older marketing-repository app copy was preserved; the actual production release builder now retains the corrected app copy.

Deployment: 6ab3188a3c9a7f6c0e2647ca.
Rollback before contact update: 6ab316984540b2e7321ef6ce.
Rollback before any wording update: 6ab30faed32eca49a5644c6f.

Full state regression was not rerun for copy-only edits; state logic, API routes, search execution and permissions are unchanged. Sales performance experiments are separate and are not approved for promotion.
