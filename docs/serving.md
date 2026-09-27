# Serving docket

These are demonstration documents: a public receipt dataset and generated invoices. The published site is a recorded demonstration on GitHub Pages. The API is an optional local service; its presence in this repository does not establish a live cloud deployment.

Set `DOCKET_WRITE_TOKEN` to a private, randomly generated value, then start `uv run uvicorn packages.api.main:app --host 127.0.0.1 --port 8080`. The default database is `docket.sqlite3`. `DATABASE_URL` can select PostgreSQL with a `postgresql+psycopg://` connection string. Tables are created at startup. The checked-in schema is the initial schema; future schema changes need an explicit migration.

`GET /health` checks a fresh database query. `GET /v1/queue` returns documents by descending risk, then creation time. `GET /v1/documents/{id}` returns extraction and rules; `GET /v1/trace/{id}` includes the trace and audit events. Uploaded redacted pixels are served at `GET /v1/documents/{id}/image`. Public seed images remain on the static site.

Write endpoints require `Authorization: Bearer YOUR_TOKEN`. With no configured token, writes are disabled. `POST /v1/documents` accepts multipart `file` with PNG, JPEG, WebP, or one PDF page, at most 10 MiB and 25 million decoded pixels. `POST /v1/extract` takes `document_id` and `backend` (`rules` or `tokens`). `POST /v1/review/{id}` takes corrected `fields`, optional `line_items`, `decision` (`accept` or `reject`), and optional `reason`.

A review transaction locks the document on PostgreSQL, updates its extraction, inserts the correction, inserts an audit event, and commits. The success response is constructed only after commit. A commit failure cannot be acknowledged as a saved correction. The SQLite implementation is for one local API process, with database locking and a busy timeout. A human accept decision is recorded separately from machine auto approval; a human acceptance does not imply that business rules passed.

`POST /v1/retrain` uses the most recent accepted correction for each document and calls the actual token training pipeline. It rejects an empty correction set. The pipeline evaluates against its fixed canonical test split and records the before/after report in the database. `POST /v1/retention` runs the expiry job. Refer to the privacy policy before training on any upload.

`CORS_ORIGINS` is an explicit comma-separated origin allowlist. Do not publish the write token in a Pages environment variable, source file, screenshot, or client bundle. Users supply it only when connecting to their own API. This token gate is deliberately minimal authentication for a demonstration.

For local PostgreSQL, set the token in your shell and run `docker compose up --build`. The database credentials in `compose.yml` are local demonstration credentials and the PostgreSQL port is not exposed to the host. Production operators must configure private credentials separately. `fly.toml` is a deployment template requiring a unique app name and separately configured database and write-token secrets.

Run `uv run python scripts/check_persistence.py` for the process-boundary check. It launches Uvicorn on loopback, uploads an in-memory generated invoice, posts a correction, then starts a separate interpreter and engine to read the document, correction, and audit. All temporary state is discarded after the check.
