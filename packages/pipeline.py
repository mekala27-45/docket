"""Serving pipeline and isolated human-correction training runs."""
import copy
import hashlib
import io
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.calibrate import FieldCalibrator
from packages.classify import CLASSIFIER_PATH, DocumentClassifier
from packages.core import AMOUNTS, FIELDS, ROOT, matches, read_json, write_json
from packages.decide import route
from packages.evaluation import interval, score_document
from packages.extract import extract
from packages.extract.rules import group_lines, numeric_token
from packages.extract.tokens import MODEL_PATH, TokenExtractor
from packages.ocr import gold_words, image_from_bytes, recognize
from packages.rules import validate_document


def process_document(document: dict[str, Any], backend: str = "rules") -> dict[str, Any]:
    doc = copy.deepcopy(document)
    tokens = doc.get("ocr_tokens", doc.get("tokens", []))
    extraction = extract(tokens, doc.get("type", "other"), backend)
    extraction["ocr_engine"] = doc.get("ocr_engine", "gold")
    FieldCalibrator.load().apply(extraction)
    reference_path = ROOT / "data/dataset.json"
    references = read_json(reference_path) if reference_path.exists() else []
    prior_documents = []
    for reference in references:
        if reference["id"] == doc.get("id"):
            break
        prior_documents.append(reference)
    rules = validate_document(doc, extraction["fields"], extraction["line_items"], known_documents=prior_documents)
    manifest_path = ROOT / "results/manifest.json"
    threshold = read_json(manifest_path).get("operating_point", {}).get("threshold", 1.000001) if manifest_path.exists() else 1.000001
    routing = route(doc, extraction, rules, threshold)
    for result in extraction["fields"].values():
        result["trace"].append({"step": "business_rules", "detail": "; ".join(f"{r['id']}: {r['status']}" for r in rules)})
        result["trace"].append({"step": "routing", "detail": routing["routing_reason"]})
    doc.update({"extraction": extraction, "rules": rules, "tokens": tokens, **routing})
    for field, result in extraction["fields"].items():
        value = result.get("value")
        if value is None and field == "vendor":
            value = "Unresolved vendor"
        elif value is None and field == "number":
            value = str(doc.get("id", "Unresolved document"))
        elif value is None and field == "currency":
            value = "Unknown"
        doc[field] = value
    doc["line_items"] = extraction["line_items"]
    doc.setdefault("created_at", datetime.now(UTC).isoformat())
    return doc


def process_image(image_bytes: bytes, filename: str) -> dict[str, Any]:
    image = image_from_bytes(image_bytes, filename)
    try:
        observation = recognize(image)
    except Exception as exc:
        raise RuntimeError("Tesseract OCR is unavailable or failed; raw upload was not stored") from exc
    if not observation["tokens"]:
        raise RuntimeError("OCR produced no words; raw upload was not stored")
    if CLASSIFIER_PATH.exists():
        classification = DocumentClassifier.load().predict(observation["tokens"])
    else:
        classification = {"type": "other", "score": 0.0, "backend": "unavailable"}
    doc = {"id": f"upload-{uuid.uuid4().hex[:12]}", "type": classification["type"], "source": "upload",
           "split": "upload", "tokens": observation["tokens"], "ocr_engine": "tesseract",
           "classification": classification, "defects": [], "filename": Path(filename).name}
    queue = process_document(doc)
    rendered = io.BytesIO()
    image.save(rendered, format="PNG")
    # The API owns redaction before any image or extraction is persisted.
    queue["_image_bytes"] = rendered.getvalue()
    return queue


def correction_document(correction: dict[str, Any]) -> dict[str, Any]:
    """Align only unambiguous reviewed values; unknown OCR tokens are masked.

    Repeated values are not assigned by overwriting competing field labels.
    Row values are matched only within the row containing its unique description.
    """
    document: dict[str, Any] = copy.deepcopy(correction["document"])
    document["split"] = "correction"
    tokens = document.get("ocr_tokens", document.get("tokens", []))
    for token in tokens:
        token["label"] = "O"
        token["training_mask"] = False
        token.pop("bio", None)
    lines = group_lines(tokens) if all("box" in token for token in tokens) else [tokens]
    positions = {id(token): index for index, token in enumerate(tokens)}
    proposals: dict[str, tuple[str, list[int]]] = {}
    excluded: list[str] = []

    def propose(key: str, field: str, value: Any, selected_lines: list[list[dict[str, Any]]]) -> list[int]:
        if value is None or str(value).strip() in {"", "[REDACTED]"}:
            excluded.append(key)
            return []
        possibilities: list[list[int]] = []
        max_words = 1 if field in AMOUNTS else max(1, len(str(value).split()) + 2)
        for line in selected_lines:
            for start in range(len(line)):
                for end in range(start + 1, min(len(line), start + max_words) + 1):
                    span = line[start:end]
                    if field in AMOUNTS and not numeric_token(span[0]):
                        continue
                    if any(token["text"] == "[REDACTED]" for token in span):
                        continue
                    if matches(" ".join(str(token["text"]) for token in span), value, field):
                        possibilities.append([positions[id(token)] for token in span])
        # Multiple matching positions are ambiguous, even if their strings agree.
        if len(possibilities) != 1:
            excluded.append(key)
            return []
        proposals[key] = (field, possibilities[0])
        return possibilities[0]

    fields = correction.get("fields", {})
    for field, raw in fields.items():
        if field not in FIELDS:
            raise ValueError("Correction contains an unsupported field")
        value = raw.get("value") if isinstance(raw, dict) else raw
        document[field] = value
        propose(field, field, value, lines)
    rows = correction.get("line_items")
    if rows is not None:
        for row_index, row in enumerate(rows):
            description = propose(f"row:{row_index}:description", "description", row.get("description"), lines)
            if not description:
                continue
            row_lines = [line for line in lines if any(positions[id(token)] in description for token in line)]
            for field in ("quantity", "unit_price", "amount"):
                if field in row:
                    propose(f"row:{row_index}:{field}", field, row[field], row_lines)
    owners: dict[int, list[str]] = {}
    for key, (_, indices) in proposals.items():
        for index in indices:
            owners.setdefault(index, []).append(key)
    matched = []
    for key, (field, indices) in proposals.items():
        if any(len(owners[index]) > 1 for index in indices):
            excluded.append(key)
            continue
        matched.append(key)
        for index in indices:
            tokens[index]["label"] = field
            tokens[index]["training_mask"] = True
    document["tokens"] = tokens
    document["line_items"] = rows or []
    document["correction_alignment"] = {"matched_fields": matched, "excluded_fields": sorted(set(excluded)),
                                        "labeled_tokens": sum(bool(t["training_mask"]) for t in tokens),
                                        "unreviewed_tokens_masked": sum(not t["training_mask"] for t in tokens)}
    return document


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _ocr_identity(tokens: list[dict[str, Any]]) -> str:
    return _digest([{key: token.get(key) for key in ("text", "box")} for token in tokens])


def retrain_from_corrections(corrections: list[dict[str, Any]]) -> dict[str, Any]:
    if not corrections:
        raise ValueError("Retraining requires at least one accepted correction")
    dataset = read_json(ROOT / "data/dataset.json")
    test = [d for d in dataset if d["split"] == "test"]
    if not test:
        raise ValueError("Retraining requires a nonempty frozen test partition")
    test_ids = {d["id"] for d in test}
    test_identities = {_ocr_identity(d["tokens"]) for d in test}
    correction_ids = [str(c["document"].get("id", "")) for c in corrections]
    if any(not value for value in correction_ids) or len(correction_ids) != len(set(correction_ids)):
        raise ValueError("Correction documents require unique nonempty IDs")
    for correction in corrections:
        doc = correction["document"]
        lineage = {doc.get(key) for key in ("id", "parent_id", "original_id", "canonical_id", "source_document_id")}
        if doc.get("split") == "test" or lineage.intersection(test_ids) or _ocr_identity(doc.get("ocr_tokens", doc.get("tokens", []))) in test_identities:
            raise ValueError("Corrections from the frozen test partition cannot train a model")
        if correction.get("decision", "accept") != "accept":
            raise ValueError("Only accepted corrections may train a model")
    aligned = [correction_document(c) for c in corrections]
    usable = [(source, doc) for source, doc in zip(corrections, aligned, strict=True) if doc["correction_alignment"]["labeled_tokens"] > 0]
    corrected = [doc for _, doc in usable]
    if not corrected:
        raise ValueError("No corrections contain unambiguous reviewed OCR spans")
    test_ocr = {d["id"]: read_json(ROOT / "results/ocr" / f"{d['id']}.json")["tokens"] for d in test}
    test_ocr_identities = {_ocr_identity(tokens) for tokens in test_ocr.values()}
    if any(_ocr_identity(doc["tokens"]) in test_ocr_identities for doc in corrected):
        raise ValueError("Corrections from the frozen test partition cannot train a model")
    corrected_ids = {d["id"] for d in corrected}
    train = [d for d in dataset if d["split"] == "train" and d["id"] not in corrected_ids]
    canonical_hash = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    baseline = TokenExtractor.load()
    candidate = TokenExtractor().fit(train + corrected)
    outcomes: list[dict[str, Any]] = []
    for document in test:
        for engine, tokens in (("gold", gold_words(document)["tokens"]), ("tesseract", test_ocr[document["id"]])):
            outcomes.append({"document_id": document["id"], "source": document["source"], "ocr_engine": engine,
                             "before": score_document(document, baseline.extract(tokens, document["type"]))["field_f1"],
                             "after": score_document(document, candidate.extract(tokens, document["type"]))["field_f1"]})
    real = [row for row in outcomes if row["ocr_engine"] == "tesseract"]
    by_source = [{"source": source, "ocr_engine": engine, "split": "test", "n_test": len(rows),
                  "before": interval([row["before"] for row in rows if row["before"] is not None], reason="No evaluable reference fields"),
                  "after": interval([row["after"] for row in rows if row["after"] is not None], reason="No evaluable reference fields"),
                  "excluded_without_reference": sum(row["before"] is None for row in rows)}
                 for source in sorted({d["source"] for d in test}) for engine in ("gold", "tesseract")
                 if (rows := [row for row in outcomes if row["source"] == source and row["ocr_engine"] == engine])]
    provenance_counts = Counter(str(source.get("provenance", {}).get("kind", "unspecified")) for source, _ in usable)
    run_id = uuid.uuid4().hex[:12]
    directory = ROOT / "artifacts/retrained" / run_id
    path = directory / "token-model.pkl"
    candidate.save(path)
    if hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() != canonical_hash:
        raise RuntimeError("Canonical model changed during the retrain run")
    report = {"before": interval([row["before"] for row in real if row["before"] is not None], reason="No evaluable reference fields"),
              "after": interval([row["after"] for row in real if row["after"] is not None], reason="No evaluable reference fields"),
              "excluded_without_reference": sum(row["before"] is None for row in real), "corrections_used": len(corrected),
              "corrections_received": len(corrections), "corrections_without_trainable_spans": len(aligned) - len(corrected),
              "human_corrections_used": provenance_counts.get("client_declared_human", 0),
              "simulated_corrections_used": provenance_counts.get("simulated_ground_truth", 0),
              "correction_provenance": dict(sorted(provenance_counts.items())),
              "human_count_definition": "Accepted reviews whose client declared human origin; reviewer identity is not verified.",
              "correction_records": [{"document_id": doc["id"], "provenance": source.get("provenance", {"kind": "unspecified"}),
                                       **doc["correction_alignment"]} for source, doc in usable],
              "n_test": len(test), "split": "test", "ocr_engine": "tesseract", "backend": "tokens",
              "by_source": by_source,
              "cord_test": next((row for row in by_source if row["source"] == "cord" and row["ocr_engine"] == "tesseract"), None),
              "frozen_test_ids_sha256": _digest(sorted(test_ids)), "frozen_test_labels_sha256": _digest(test),
              "frozen_test_ocr_sha256": _digest(test_ocr), "canonical_model_sha256": canonical_hash,
              "model_path": path.relative_to(ROOT).as_posix(), "run_id": run_id,
              "canonical_model_changed": False,
              "labeling_method": "Only unique reviewed field/row spans train; ambiguous, redacted and unreviewed OCR tokens are masked. Both models use identical frozen test labels and OCR."}
    write_json(directory / "report.json", report)
    return report
