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

## Optional review-to-training run

Pages remains the selected deployment. Browser practice reviews do not become server training examples, and the published simulated correction example is not evidence of human reviews.

For a local API collection, submit actual reviews with `review_source: "human"`. Scripted checks must use `integration_test`, and simulated labels must stay `simulation`. Review provenance is a client declaration; it does not authenticate a particular person. When upgrading an existing local database, startup adds snapshot/provenance columns. Legacy corrections without that evidence remain excluded; review them again if they should be included.

With the API running on the port shown above and `DOCKET_WRITE_TOKEN` set in the shell, run:

```text
uv run python scripts/retrain_from_corrections.py --api-url http://127.0.0.1:8000 --provenance client_declared_human
```

Use `--provenance simulated_ground_truth` only when intentionally evaluating simulated examples, or `all` to include all existing origins while keeping their separate counts. The command refuses an empty selected collection. It saves the exact private export and before/after report under ignored `artifacts/retrain-command/`; an explicit `--output` can choose another private directory. An existing export can be replayed with `--corrections <path>`.

Check `human_corrections_used`, `simulated_corrections_used`, `corrections_without_trainable_spans`, and each correction's alignment exclusions before interpreting the result. Read `cord_test` for CORD alone rather than treating the mixed generated/receipt aggregate as a receipt benchmark. Compare both OCR columns in `by_source`. The report identifies frozen test inputs by hashes and keeps the canonical model unchanged. No model is promoted automatically.

If the API reports that accepted corrections changed after export, rerun the command to capture the current collection. If every selected correction is unalignable, inspect its OCR and supplied values; do not force an unmatched value onto an arbitrary token. Never relabel simulated or automated examples as human to make the count nonzero.
