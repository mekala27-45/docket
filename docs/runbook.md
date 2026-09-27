# Runbook

## Published demo

The site is deployed by GitHub Actions from the `main` branch. A release must pass the validation job before the Pages artifact is deployed. Check the action's deployment URL and open the inbox and a reviewer page after publication.

The recorded dataset is public and immutable at runtime. Review practice changes are local to the browser. Reset the browser's demo state to return to the canonical session. Changes to that local state do not train a remote model.

## Local API

Install dependencies with `uv sync --python 3.12`, copy `.env.example` to `.env`, and configure a nonempty write token. Set `DATABASE_URL` to a persistent SQLite path for local use or a PostgreSQL connection string for a server. Set allowed CORS origins explicitly. Run `uv run uvicorn packages.api.main:app --host 127.0.0.1 --port 8000`.

Use the included Docker configuration when Tesseract is not installed on the host. Keep upload storage persistent only after redaction; never publish local databases. Test the independent-connection persistence check before connecting a shared service.

## Recovery

If the API is unavailable, the site remains a recorded demo. Do not silently claim that browser-local edits reached the service. If a report drift check fails, regenerate reports from the manifest and review the diff. If measurements change unexpectedly, compare split membership, OCR version, and the seed before interpreting the change as a model improvement.

To revert a bad Pages release, revert the offending commit and allow the same workflow to validate and deploy it. No cloud API rollback is needed for the recorded deployment.

Demonstration documents only. Generated invoices contain fictional vendors and transactions. Public CORD receipts are attributed separately.
