# Field and decision policy

A document is one recorded page with a stable ID, source, and split. A token is a word with text, a normalized page box, and an OCR score. A field is one named value assembled from candidate tokens. A line item is one row containing a description, quantity, unit price, and amount.

## Match policy

Exact matching compares the extracted and labeled values before normalization. Normalized matching uses `packages.core.normalize`: whitespace is collapsed, text is case-folded, dates are parsed into ISO form, and amounts use decimal parsing. Indonesian thousands separators are recognized for the receipt population. Empty truth does not count as a successful match. Locale inference can still be ambiguous; this is a documented baseline, not a universal accounting parser.

Document success requires every required field to match. Invoice fields are vendor, number, date, due date, currency, subtotal, tax, and total. Purchase orders use that set without due date. Receipts require total because CORD's receipt annotations do not provide every invoice header field. A higher receipt document-success rate therefore does not represent an equally difficult task. Unknown document types do not qualify for automatic approval.

## CORD label mapping

The recorded ingestion retains original labels and boxes. `menu.nm` maps to description, `menu.cnt` to quantity, `menu.unitprice` to unit price, and `menu.price` to line amount. `sub_total.subtotal_price` maps to subtotal, tax-related subtotal labels to tax, and `total.total_price` to total. Unsupported labels remain other. No vendor or invoice-number truth is invented for missing labels. See the actual mapping in `scripts/build_dataset.py` and provenance under `data/cord`.

## Routing and duplicate policy

Confidence is a probability estimate evaluated against held-out outcomes. It is not a guarantee. The operating threshold is selected using the development split and the stated review/error costs. A page can qualify for automatic approval only when required fields satisfy the threshold and business checks pass.

Duplicate checks use normalized document identifiers and vendor evidence, with amount and image-hash checks where the data is available. Missing master data is not evidence that a vendor or purchase order is valid. Generated documents have an explicit fictional vendor and purchase-order master. Uploads do not acquire a verified master simply by repeating what OCR read.

Demonstration documents only. Generated invoices contain fictional vendors and transactions. Public CORD receipts are attributed separately.
