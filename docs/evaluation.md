# Evaluation protocol

The committed `results/manifest.json` is the publication source. The report renderer validates populations, measured intervals, and split discipline before rendering complete documents. Its check mode compares whole files and rejects unexplained publication edits.

Each extractor is measured on gold words and Tesseract words. Gold annotations isolate extraction behavior; OCR observations include recognition errors. The same normalized field definitions and document-level sample units are used in both columns. Results identify generated documents separately from the bounded CORD receipt population.

Training fits the learned token model. Validation fits calibration and selects a routing threshold using the stated costs. Test observations report the selected policy. Test data must not select the threshold, and a deliberate test-selection mutation is rejected by the publication gate.

Intervals quantify sampling uncertainty on the recorded population. They do not cover changes in vendors, language, imaging equipment, template design, or financial loss assumptions. A small number of automatically approved pages cannot establish a production error rate. An empty automatically approved group has no observable conditional error rate and must be reported as unavailable.

The degradation sweep uses generated images with known truth. It changes blur, skew, compression, resolution, noise, and photographed-page transforms at recorded levels. Results apply to those images and parameters. A single-document illustration in the browser is not a population estimate.

Reviewer corrections can become training examples only for the optional API's explicit retraining path. Browser practice is excluded from the canonical benchmark. A training improvement is not guaranteed, and the before/after report must preserve a decline when one occurs.

Rule labels include direct consequences of each injected defect: changing an invoice total creates both an arithmetic failure and a mismatch with the independently recorded purchase-order total. These propagated consequences are expected positives, not false alarms. Receipt header fields absent from CORD labels receive no generated-header calibration claim; they require review.

Demonstration documents only. Generated invoices contain fictional vendors and transactions. Public CORD receipts are attributed separately.
