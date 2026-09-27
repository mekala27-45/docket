"""Serving pipeline and isolated human-correction training runs."""
import copy
import io
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.calibrate import FieldCalibrator
from packages.classify import CLASSIFIER_PATH, DocumentClassifier
from packages.core import ROOT, matches, read_json, write_json
from packages.decide import route
from packages.evaluation import interval, score_document
from packages.extract import extract
from packages.extract.tokens import TokenExtractor
from packages.ocr import image_from_bytes, recognize
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
        elif value is None and field == "total":
            value = 0
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
    document: dict[str, Any] = copy.deepcopy(correction["document"])
    document["split"] = "correction"
    tokens = document.get("ocr_tokens", document.get("tokens", []))
    for token in tokens:
        token["label"] = "O"
        token.pop("bio", None)
    fields = correction.get("fields", {})
    for field, raw in fields.items():
        value = raw.get("value") if isinstance(raw, dict) else raw
        document[field] = value
        words = str(value).split()
        for index, token in enumerate(tokens):
            if field in {"subtotal", "tax", "total"} and matches(token["text"], value, field):
                token["label"] = field
            elif words and index + len(words) <= len(tokens):
                phrase = " ".join(t["text"] for t in tokens[index:index + len(words)])
                if matches(phrase, value, field):
                    for selected in tokens[index:index + len(words)]:
                        selected["label"] = field
    document["tokens"] = tokens
    document["line_items"] = correction.get("line_items", document.get("line_items", []))
    return document


def retrain_from_corrections(corrections: list[dict[str, Any]]) -> dict[str, Any]:
    if not corrections:
        raise ValueError("Retraining requires at least one accepted correction")
    dataset = read_json(ROOT / "data/dataset.json")
    test = [d for d in dataset if d["split"] == "test"]
    test_ids = {d["id"] for d in test}
    if any(c["document"].get("id") in test_ids or c["document"].get("split") == "test" for c in corrections):
        raise ValueError("Corrections from the frozen test partition cannot train a model")
    corrected = [correction_document(c) for c in corrections]
    corrected_ids = {d["id"] for d in corrected}
    train = [d for d in dataset if d["split"] == "train" and d["id"] not in corrected_ids]
    baseline = TokenExtractor.load()
    candidate = TokenExtractor().fit(train + corrected)
    before, after = [], []
    for document in test:
        tokens = read_json(ROOT / "results/ocr" / f"{document['id']}.json")["tokens"]
        before.append(score_document(document, baseline.extract(tokens, document["type"]))["field_f1"])
        after.append(score_document(document, candidate.extract(tokens, document["type"]))["field_f1"])
    run_id = uuid.uuid4().hex[:12]
    directory = ROOT / "artifacts/retrained" / run_id
    path = directory / "token-model.pkl"
    candidate.save(path)
    report = {"before": interval(before), "after": interval(after), "corrections_used": len(corrected),
              "n_test": len(test), "split": "test", "ocr_engine": "tesseract", "backend": "tokens",
              "model_path": path.relative_to(ROOT).as_posix(), "run_id": run_id,
              "canonical_model_changed": False,
              "labeling_method": "Corrected values aligned to matching OCR token spans; unmatched spans excluded"}
    write_json(directory / "report.json", report)
    return report
