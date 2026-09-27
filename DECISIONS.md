# Decisions

## 2026-09-26: GitHub Pages as the published product

The owner explicitly chose the recorded demo after reviewing the live API hosting dependency. The site must be useful on its own, and its review actions must say when they are saved in the browser. Fly and Neon provisioning is outside the selected deployment scope.

## 2026-09-26: Independent project

The surrounding directory contains several unrelated portfolio repositories and uncommitted work. Docket has its own repository and dependency locks so building it does not alter those projects.

## 2026-09-26: Reverse the default Python selection

The first environment selected Python 3.14. PyArrow attempted a native build and Windows blocked that interpreter. The build was changed to the existing Python 3.12 runtime and an isolated environment. This is an environment failure, not an OCR result.

## 2026-09-26: Two extraction inputs

Gold words isolate extraction quality; Tesseract words measure the full path. Both use the same field definitions. Results must never label gold words as engine output.

## 2026-09-26: Bounded receipt data

The public dataset is much larger than the portable demonstration needs. Record the actual source rows and split coverage, and state any sample limits. Do not extrapolate a subset measurement to the full CORD benchmark.

## 2026-09-26: Separate truth and predictions

Generated truth includes fields and tokens so errors can be measured exactly. Prediction paths must consume tokens and image evidence, never copy the truth fields into extraction output.

## 2026-09-26: Choose routing on development data

The cost of a review and a mistaken automatic approval are policy inputs. Choose a threshold on development data, freeze it, and evaluate on test data. Small samples and wide intervals should remain visible.

## 2026-09-26: Query-string reviewer routes

A static export cannot pre-render arbitrary future upload IDs. The reviewer uses a static route and a document query parameter, supporting both recorded and API documents without a server-rendered page.

## 2026-09-26: White document canvas in both themes

The page remains white so overlay identity and document contrast are stable. The interface may switch themes. Field labels supplement colors, and amounts use aligned tabular digits.

## 2026-09-26: Reverse the cloud-first build assumption

The reference proposed provisioning a cloud API before building the interface. After the owner selected GitHub Pages with a recorded demo, that dependency was removed. The runnable API remains a separate capability and is tested locally.

## 2026-09-26: No invented model integration

A model that did not run has no score. The optional vision extractor cannot appear as a measured competitor without credentials, validated outputs, and evaluation on the same labels.

Demonstration documents only. Generated invoices contain fictional vendors and transactions. Public CORD receipts are attributed separately.
