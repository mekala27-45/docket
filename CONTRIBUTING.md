# Contributing

Use Python 3.12 and the committed uv lockfile. Install the web dependencies with `npm ci` from `web`. Keep generated ground truth separate from model inputs. New extraction backends must return the common trace format and be evaluated on both gold words and real OCR.

Run Python behavior tests, Ruff, strict mypy, the report drift gate, and the web type check and browser tests before publishing. Do not commit credentials, unredacted uploads, local review databases, or environment folders. When changing evaluation inputs, regenerate the manifest and the reports together and explain population or protocol changes.

Business rules need a passing example, a deliberate defect, and an empty-input refusal. Persistence tests must observe committed data from a separate connection. Browser-local review state is not proof of API durability.

Demonstration documents only. Generated invoices contain fictional vendors and transactions. Public CORD receipts are attributed separately.
