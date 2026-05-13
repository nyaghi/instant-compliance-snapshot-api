# CharityClarity Staging

Staging URL target: `https://staging.compliance-express.com`

Staging is intended to be an exact copy of production plus the state or feature currently under test. It must not be used as a separate hand-edited version of CharityClarity.

## Access

Staging uses the same internal access pattern as CharityClarity internal tools:

- Email must end with `@compliance-express.com`
- Passcode must be `8977`

The staging frontend blocks submissions until those values are entered.

The staging backend must also run with:

```text
CE_STAGING_ACCESS_REQUIRED=1
```

That backend setting rejects API requests unless the email is a Compliance Express email and the passcode is correct.

## Files

Backend staging blueprint:

`deployment/render.staging.yaml`

Frontend staging source:

`frontend/instant-compliance-snapshot-staging.html`

Frontend staging publish folder:

`deployment/staging-netlify/index.html`

After editing `frontend/instant-compliance-snapshot-staging.html`, sync the Netlify publish copy:

```powershell
powershell -ExecutionPolicy Bypass -File deployment\sync-staging-frontend.ps1
```

Production frontend remains:

`frontend/instant-compliance-snapshot-netlify-latest.html`

## Deployment Shape

Recommended permanent setup:

1. Render service: `instant-compliance-snapshot-api-staging`
2. Netlify site: `staging.compliance-express.com`
3. Netlify publish directory: `deployment/staging-netlify`
4. DNS: CNAME `staging` to the Netlify staging site hostname

Interim operational setup:

`https://compliance-express-staging.netlify.app`

This staging frontend currently uses the production API after the staging access gate:

`https://instant-compliance-snapshot-api.onrender.com`

This makes the page usable while the separate Render staging backend is pending.

Target final setup:

`https://instant-compliance-snapshot-api-staging.onrender.com`

If Render assigns a different staging URL, update both:

- `frontend/instant-compliance-snapshot-staging.html`
- `deployment/staging-netlify/index.html`

## Workflow For Adding A State

1. Start from the current production baseline.
2. Deploy the unchanged baseline to staging.
3. Confirm staging behaves like production.
4. Add the new state in a feature branch or staging branch.
5. Update the backend `SUPPORTED_STATES` and the frontend state checkbox list.
6. Run targeted smoke tests for the new state.
7. Run regression tests for existing states.
8. Deploy to staging and test from `staging.compliance-express.com`.
9. Promote the same tested code to production.

Do not manually recreate changes in production. Promote the tested code.
