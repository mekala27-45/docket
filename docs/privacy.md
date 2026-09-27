# Privacy policy for the demonstration

These are demonstration documents: a public receipt dataset and generated invoices. No real customer, vendor or transaction appears in the generated examples. The CORD receipts are public research data and retain their separate attribution.

The GitHub Pages demonstration has no upload server. Browser practice corrections stay in that browser. A separately configured API accepts uploads only with its write token. Never upload a real person's document to this demonstration.

The API decodes uploads in memory, runs OCR, then detects card-like numbers, account/routing/identifier numbers, US SSN-like numbers, and email addresses. Matching OCR boxes are painted black. Text values, including extraction traces and review reasons, are sanitized before the database transaction. Images are re-encoded as PNG to remove metadata. Raw bytes and original filenames are never written to the database or filesystem. Empty OCR or an unusable redaction box rejects the upload.

This is a pattern-based demonstration. It cannot guarantee detection of names, addresses, handwriting, identifiers missed by OCR, or every jurisdiction's identifier format. It is not suitable for production personal data processing. Planted identifiers test the supported patterns and pixel masking; they do not establish complete PII recall.

Upload images, extracted text, review corrections, and their document audit events expire after 24 hours. While the API runs, a retention task checks once per minute and on startup. Offline time can delay physical deletion until the next startup. Seeded demonstration records do not expire. The token-gated retention endpoint allows an operator to trigger deletion immediately when due. Retrained model artifacts have separate retention and are not a mechanism for erasing learned features; do not use sensitive uploads for training.

The SQLite database is local by default. Optional PostgreSQL stores the same data and redacted image bytes transactionally. Transport security, database access policy, backup retention, and write-token rotation belong to the operator of a separately deployed API. The public GitHub Pages site has no server credentials embedded in its bundle.

Evidence: `tests/test_redact.py`, `tests/test_api.py::test_review_redacts_sensitive_reason_and_fields`, `tests/test_api.py::test_retention_deletes_only_expired_uploads`, and the independent-process persistence check.
