# Instant Compliance Snapshot API

Backend service for the Compliance Express Instant Compliance Snapshot tool.

## Render setup

Create a Render Web Service from this folder/repository.

Build command:

```bash
pip install -r requirements.txt && python -m playwright install --with-deps chromium
```

Start command:

```bash
python registry_snapshot_server.py
```

Environment variables:

```text
HOST=0.0.0.0
PUBLIC_BASE_URL=https://instant-compliance-snapshot-api.onrender.com
PYTHONUNBUFFERED=1
```

`PUBLIC_BASE_URL` must match the public Render URL so evidence PDF links work from the Compliance Express website.
