"""Fit on train, calibrate/select on validation, report once on untouched test labels."""
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix

from packages.calibrate import FieldCalibrator, reliability
from packages.classify import LABELS, DocumentClassifier, letters
from packages.core import FIELDS, ROOT, SEED, matches, read_json, required_fields, write_json
from packages.decide import choose_threshold, document_confidence
from packages.evaluation import (
    benjamini_hochberg,
    fields_to_score,
    interval,
    ocr_error,
    paired_comparison,
    proportion_interval,
    score_document,
    summarize,
)
from packages.extract import extract
from packages.extract.tokens import TokenExtractor
from packages.ocr import gold_words
from packages.rules import validate_document


def run() -> dict[str, Any]:
    dataset = read_json(ROOT / "data/dataset.json")
    observations = {d["id"]: read_json(ROOT / "results/ocr" / f"{d['id']}.json") for d in dataset}
    train = [d for d in dataset if d["split"] == "train"]
    token_model = TokenExtractor().fit(train)
    token_model.save()
    print(f"Trained token model on {len(train)} documents", flush=True)
    predictions: dict[tuple[str, str, str], dict[str, Any]] = {}
    scored = []
    calibration_rows = []
    calibration_variants = read_json(ROOT / "data/generated/calibration/annotations.json")
    sweep = read_json(ROOT / "data/generated/sweep/annotations.json")
    sweep_config = read_json(ROOT / "data/generated/sweep/config.json")
    parents = {d["id"]: d["split"] for d in dataset}
    for partition, variants in (("validation", calibration_variants), ("test", sweep)):
        if not variants or any(d["split"] != partition or parents.get(d["parent_id"]) != partition for d in variants):
            raise ValueError("Degraded variants must retain their parent document's held-out partition")
    for document in dataset:
        if document["split"] == "train":
            continue
        for backend in ("rules", "tokens"):
            for engine in ("gold", "tesseract"):
                tokens = gold_words(document)["tokens"] if engine == "gold" else observations[document["id"]]["tokens"]
                prediction = extract(tokens, document["type"], backend, token_model)
                prediction["ocr_engine"] = engine
                predictions[(document["id"], backend, engine)] = prediction
                score = score_document(document, prediction)
                scored.append({**score, "source": document["source"], "backend": backend,
                               "ocr_engine": engine, "split": document["split"], "type": document["type"]})
                if document["split"] == "validation" and engine == "tesseract":
                    for field in fields_to_score(document):
                        calibration_rows.append({"field": field, "backend": backend,
                                                 "score": prediction["fields"][field]["confidence"],
                                                 "correct": score["fields"][field], "population": document["source"],
                                                 "parent_id": document["id"], "split": "validation"})
    for document in [*calibration_variants, *sweep]:
        observation = read_json(ROOT / "results/ocr" / f"{document['id']}.json")
        for backend in ("rules", "tokens"):
            prediction = extract(observation["tokens"], document["type"], backend, token_model)
            prediction["ocr_engine"] = "tesseract"
            predictions[(document["id"], backend, "tesseract")] = prediction
            # Each baseline already appears as its clean parent. Do not count it six times.
            if document["split"] == "validation" and document.get("level_index", 0) > 0:
                for field in fields_to_score(document):
                    calibration_rows.append({"field": field, "backend": backend,
                        "score": prediction["fields"][field]["confidence"],
                        "correct": int(matches(prediction["fields"][field]["value"], document[field], field)),
                        "population": "generated", "parent_id": document["parent_id"], "split": "validation"})
    calibrator = FieldCalibrator().fit(calibration_rows)
    calibrator.save()
    for prediction in predictions.values():
        calibrator.apply(prediction)
    extraction_table = []
    per_field = []
    for source in ("generated", "cord"):
        for backend in ("rules", "tokens"):
            for engine in ("gold", "tesseract"):
                rows = [r for r in scored if r["source"] == source and r["backend"] == backend
                        and r["ocr_engine"] == engine and r["split"] == "test"]
                extraction_table.append({"source": source, "backend": backend, "ocr_engine": engine,
                                         "split": "test", "n": len(rows), **summarize(rows)})
                for field in FIELDS:
                    outcomes = [r["fields"][field] for r in rows if field in r["fields"]]
                    if outcomes:
                        per_field.append({"source": source, "backend": backend, "ocr_engine": engine,
                                          "field": field, "normalized_match": interval(outcomes)})
    test = [d for d in dataset if d["split"] == "test"]
    ocr_table = []
    for source in ("generated", "cord"):
        documents = [d for d in test if d["source"] == source]
        errors = [ocr_error(d["tokens"], observations[d["id"]]["tokens"]) for d in documents]
        ocr_table.append({"source": source, "engine": "tesseract", "n": len(errors), "split": "test",
                          "version": observations[documents[0]["id"]]["version"],
                          "preprocessing": observations[documents[0]["id"]]["preprocessing"],
                          "cer": interval([e["cer"] for e in errors]), "wer": interval([e["wer"] for e in errors])})
    calibration_table = []
    for backend, population in ((b, s) for b in ("rules", "tokens") for s in ("generated", "cord")):
        for field in FIELDS:
            docs = [d for d in [*test, *(d for d in sweep if d.get("level_index", 0) > 0)]
                    if d["source"] == population and field in fields_to_score(d)]
            if not docs:
                continue
            outcomes = [int(matches(predictions[(d["id"], backend, "tesseract")]["fields"][field]["value"], d[field], field))
                        for d in docs]
            raw = [predictions[(d["id"], backend, "tesseract")]["fields"][field]["raw_confidence"] for d in docs]
            calibrated = [predictions[(d["id"], backend, "tesseract")]["fields"][field]["confidence"] for d in docs]
            parent_ids = [d.get("parent_id", d["id"]) for d in docs]
            measured = reliability(calibrated, outcomes, groups=parent_ids if population == "generated" else None)
            calibration_table.append({"field": field, "backend": backend, "n": len(docs), "split": "test",
                                      "population": population, "independent_documents": len(set(parent_ids)),
                                      "scope": "clean_and_degraded" if population == "generated" else "original",
                                      "fitted_on": "validation", "ece_before": reliability(raw, outcomes)["ece"],
                                      "ece_after": measured["ece"], "bins": measured["bins"]})
    routing_records: dict[str, list[dict[str, Any]]] = {"validation": [], "test": []}
    rules_records = []
    for doc in dataset:
        if doc["split"] not in routing_records:
            continue
        prediction = predictions[(doc["id"], "rules", "tesseract")]
        prior_documents = dataset[:next(i for i, previous in enumerate(dataset) if previous["id"] == doc["id"])]
        rules = validate_document(doc, prediction["fields"], prediction["line_items"], known_documents=prior_documents)
        required = required_fields(doc["type"])
        routing_records[doc["split"]].append({"document_id": doc["id"], "source": doc["source"],
            "confidence": document_confidence(doc, prediction), "rules_pass": all(r["status"] in {"pass", "not_applicable"} for r in rules),
            "required_present": bool(required) and all(prediction["fields"].get(f, {}).get("value") is not None for f in required),
            "correct": score_document(doc, prediction)["document_success"] == 1 and not doc.get("defects")})
        for rule in rules:
            rules_records.append({**rule, "document_id": doc["id"], "source": doc["source"], "split": doc["split"],
                                  "expected_defect": rule["id"] in doc.get("defects", [])
                                  or (rule["id"] == "purchase_order" and "arithmetic" in doc.get("defects", []))})
    operating = choose_threshold(routing_records["validation"])
    approved = [r for r in routing_records["test"] if r["rules_pass"] and r["required_present"]
                and r["confidence"] >= operating["threshold"]]
    n_test = len(test)
    operating.update({"reported_on": "test", "backend": "rules", "ocr_engine": "tesseract", "n": n_test,
                       "auto_approved": len(approved),
                       "review_rate": proportion_interval(n_test - len(approved), n_test),
                       "auto_approval_error": proportion_interval(sum(not r["correct"] for r in approved), len(approved),
                                                                    "No auto-approved test documents"),
                       "correctness": "All required normalized fields correct and no planted business defect"})
    operating["by_source"] = []
    for source in ("generated", "cord"):
        population_records = [r for r in routing_records["test"] if r["source"] == source]
        population_approved = [r for r in approved if r["source"] == source]
        operating["by_source"].append({"source": source, "n": len(population_records),
            "auto_approved": len(population_approved),
            "review_rate": proportion_interval(len(population_records) - len(population_approved), len(population_records)),
            "auto_approval_error": proportion_interval(sum(not r["correct"] for r in population_approved), len(population_approved),
                                                       "No auto-approved documents in this population")})
    rule_scorecard = []
    for rule_id in sorted({r["id"] for r in rules_records}):
        rows = [r for r in rules_records if r["id"] == rule_id and r["source"] == "generated" and r["split"] == "test"]
        tp = sum(r["status"] == "fail" and r["expected_defect"] for r in rows)
        fired = sum(r["status"] == "fail" for r in rows)
        expected = sum(r["expected_defect"] for r in rows)
        rule_scorecard.append({"id": rule_id, "name": rows[0]["name"], "n": len(rows), "source": "generated",
                               "split": "test", "precision": proportion_interval(tp, fired, "Rule did not fire"),
                               "recall": proportion_interval(tp, expected, "No planted defects for this rule"),
                               "fired": fired, "expected": expected, "tp": tp, "fp": fired - tp,
                               "fn": expected - tp, "tn": len(rows) - fired - expected + tp,
                               "truth": "Injected business defects, including PO amount mismatch caused by wrong total",
                               "not_evaluable": sum(r["status"] == "not_evaluable" for r in rows)})
    comparisons = []
    for source in ("generated", "cord"):
        for engine in ("gold", "tesseract"):
            selected = [r for r in scored if r["source"] == source and r["ocr_engine"] == engine and r["split"] == "test"]
            left = [r["field_f1"] for r in selected if r["backend"] == "tokens"]
            right = [r["field_f1"] for r in selected if r["backend"] == "rules"]
            comparisons.append({"source": source, "ocr_engine": engine, **paired_comparison(left, right)})
    for comparison, adjusted in zip(comparisons, benjamini_hochberg([r["p_value"] for r in comparisons]), strict=True):
        comparison["q_value"] = adjusted
    classifier = DocumentClassifier().fit(train + letters("train", 24))
    classifier.save()
    class_docs = [{**d, "tokens": observations[d["id"]]["tokens"]} for d in test] + letters("test", 12)
    truth = [d["type"] for d in class_docs]
    predicted_types = [classifier.predict(d["tokens"])["type"] for d in class_docs]
    classification = {"labels": LABELS, "confusion_matrix": confusion_matrix(truth, predicted_types, labels=LABELS).tolist(),
                      "accuracy": interval([a == b for a, b in zip(truth, predicted_types, strict=True)]),
                      "n": len(truth), "split": "test", "report": classification_report(truth, predicted_types, labels=LABELS,
                                                                                         output_dict=True, zero_division=0),
                      "population": "Generated invoice/PO images, public CORD receipt images and synthetic letter tokens"}
    print("Computed extraction, calibration, operating point and classification", flush=True)
    sweep_records = []
    for document in sweep:
        observation = read_json(ROOT / "results/ocr" / f"{document['id']}.json")
        error = ocr_error(document["tokens"], observation["tokens"])
        for backend in ("rules", "tokens"):
            extraction = predictions[(document["id"], backend, "tesseract")]
            sweep_records.append({"id": document["id"], "parent_id": document["parent_id"],
                                  "kind": document["degradation"], "level": document["level"],
                                  "level_index": document["level_index"], "backend": backend,
                                  **error, **score_document(document, extraction)})
    degradation = []
    for kind in sorted({r["kind"] for r in sweep_records}):
        for level in sorted({r["level"] for r in sweep_records if r["kind"] == kind}):
            for backend in ("rules", "tokens"):
                rows = [r for r in sweep_records if r["kind"] == kind and r["level"] == level and r["backend"] == backend]
                degradation.append({"kind": kind, "level": level, "backend": backend, "n": len(rows),
                                    "level_index": rows[0]["level_index"],
                                    "field_f1": interval([r["field_f1"] for r in rows]),
                                    "cer": interval([r["cer"] for r in rows]),
                                    "document_success": interval([r["document_success"] for r in rows]),
                                    "image": f"/data/images/{rows[0]['id']}.png", "document_id": rows[0]["parent_id"]})
    floors = []
    for kind in sorted({r["kind"] for r in degradation}):
        for backend in ("rules", "tokens"):
            rows = [r for r in degradation if r["kind"] == kind and r["backend"] == backend]
            rows.sort(key=lambda r: r["level"], reverse=kind in {"jpeg", "downscale"})
            broken = [r for r in rows if r["field_f1"]["value"] < .8]
            floors.append({"kind": kind, "backend": backend, "floor": .8,
                           "first_below": broken[0]["level"] if broken else None,
                           "reason": None if broken else "No observed level fell below the floor"})
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(), "seed": SEED,
        "scope": {source: {split: sum(d["source"] == source and d["split"] == split for d in dataset)
                            for split in ("train", "validation", "test")} for source in ("generated", "cord")},
        "extraction": extraction_table, "per_field": per_field, "ocr": ocr_table, "operating_point": operating,
        "calibration": calibration_table, "degradation": degradation, "degradation_floors": floors,
        "degradation_policy": {"field_f1_floor": .8, "levels_per_type": len(next(iter(sweep_config["parameters"].values()))["levels"]),
                               "parameters": sweep_config["parameters"], "source": "generated", "split": "test",
                               "independent_documents_per_level": len({d["parent_id"] for d in sweep}),
                               "protocol": "All 24 generated test parents at each preselected severity; no level tuning on test"},
        "calibration_protocol": {"fitted_on": "validation", "generated_parents": len({d["parent_id"] for d in calibration_variants}),
                                 "cord_parents": sum(d["source"] == "cord" and d["split"] == "validation" for d in dataset),
                                 "generated_variants": len([d for d in calibration_variants if d["level_index"] > 0]),
                                 "test_variants": len([d for d in sweep if d["level_index"] > 0]),
                                 "method": "Per-backend, per-population, per-field isotonic regression; missing values fail closed. "
                                           "Generated reliability intervals resample parent documents, retaining their variants. "
                                           "Routing is selected and reported on the original document populations."},
        "classification": classification, "rules": rule_scorecard, "comparisons": comparisons,
        "optional_vision": {"available": False, "reason": "No paid vision model configured; not evaluated"},
        "latency": {"ocr_ms": interval([observations[d["id"]]["elapsed_ms"] for d in test]),
                    "method": "Tesseract subprocess wall time in 4-worker local Docker batch; not API load latency"},
    }
    manifest["scope"]["limitations"] = [
        "Full original CORD 800/100/100 splits are used, with a project-specific subtotal/tax/total and line-item mapping, not the official benchmark metric.",
        "Generated invoices share four templates; performance does not establish generalization to unseen vendors or layouts.",
        "Small test populations give wide intervals; the chosen costs are illustrative (review 1, wrong approval 20).",
        "CORD gold words cover annotated semantic lines; full-page OCR CER/WER includes unannotated text.",
        "Gold/real OCR input gaps include token segmentation and layout conventions, so they are not pure additive character-recognition loss.",
        "Rules are conservative on receipts without invoice date, vendor and PO evidence, so those receipts go to review.",
        "Other-class classification uses generated text tokens; no real miscellaneous mailroom documents were evaluated.",
        "Extraction measurements condition on the reference document type; document classification is measured separately.",
        "No live cloud API is deployed. The GitHub Pages demo records this run and stores review practice in the browser.",
        "Retrain demonstration uses simulated corrections from validation truth; no human corrections are claimed.",
        "Generated calibration includes controlled image variants from 24 validation parents; these are correlated observations, not new independent documents.",
    ]
    write_json(ROOT / "results/manifest.json", manifest)
    pd.DataFrame([{k: v for k, v in r.items() if k != "fields"} for r in scored]).to_parquet(ROOT / "results/extraction.parquet", index=False)
    pd.DataFrame(sweep_records).drop(columns="fields").to_parquet(ROOT / "results/degradation.parquet", index=False)
    pd.DataFrame(rules_records).to_parquet(ROOT / "results/rules.parquet", index=False)
    from packages.pipeline import process_document, retrain_from_corrections
    corrected = [d for d in dataset if d["split"] == "validation" and d["source"] == "generated"][:8]
    corrections = [{"document": {**d, "tokens": observations[d["id"]]["tokens"]},
                    "fields": {f: d[f] for f in FIELDS if f in d}, "line_items": d["line_items"],
                    "provenance": {"kind": "simulated_ground_truth"}} for d in corrected]
    manifest["retrain"] = retrain_from_corrections(corrections)
    candidate_path = ROOT / "results/models/retrained-demo.pkl"
    shutil.copy2(ROOT / manifest["retrain"]["model_path"], candidate_path)
    manifest["retrain"]["model_path"] = candidate_path.relative_to(ROOT).as_posix()
    manifest["retrain"]["correction_source"] = "Simulated corrections from eight validation documents with known truth"
    write_json(ROOT / "results/manifest.json", manifest)
    documents = []
    public_images = ROOT / "web/public/data/images"
    public_images.mkdir(parents=True, exist_ok=True)
    for document in test:
        queue = process_document({**document, "ocr_tokens": observations[document["id"]]["tokens"], "ocr_engine": "tesseract"})
        queue.pop("ocr_tokens", None)
        # Gold labels and internal masters are not needed by the browser.
        for key in ("image_path", "pdf_path", "vendor_master", "vendor_currencies", "po_reference", "expected_po_total"):
            queue.pop(key, None)
        documents.append(queue)
        shutil.copy2(ROOT / document["image_path"], public_images / Path(document["image_path"]).name)
    for document in sweep:
        if document["parent_id"] == sweep[0]["parent_id"]:
            shutil.copy2(ROOT / document["image_path"], public_images / Path(document["image_path"]).name)
    documents.sort(key=lambda d: (d["status"] != "needs_review", -d["risk"]))
    write_json(ROOT / "web/public/data/demo.json", {"documents": documents, "evaluation": manifest})
    print(json.dumps({"documents": len(documents), "operating_point": operating, "retrain": manifest["retrain"]}, indent=2), flush=True)
    return manifest


if __name__ == "__main__":
    run()
