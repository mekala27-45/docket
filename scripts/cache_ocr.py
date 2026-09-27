"""Run real Tesseract once per committed image, in native Python or the OCR container."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytesseract
from PIL import Image

from packages.ocr import recognize

ROOT = Path(__file__).resolve().parents[1]
PREPROCESSING_SIGNATURE = "exif-rgb-upscale900-psm6-eng-v1"


def one(document: dict[str, Any], engine_version: str | None = None) -> dict[str, Any]:
    dest = ROOT / "results/ocr" / f"{document['id']}.json"
    source = ROOT / document["image_path"]
    image_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    version = engine_version or str(pytesseract.get_tesseract_version())
    if dest.exists():
        existing = json.loads(dest.read_text(encoding="utf-8"))
        if (existing.get("image_sha256") == image_sha256
                and existing.get("preprocessing_signature") == PREPROCESSING_SIGNATURE
                and existing.get("version") == version and not existing.get("error")):
            return {"id": document["id"], "cached": True, "error": None}
    start = time.perf_counter()
    error = None
    try:
        with Image.open(source) as image:
            record = recognize(image)
    except (RuntimeError, OSError, ValueError) as exc:
        # Failed pages are retained as failed observations, never silently omitted.
        error = f"{type(exc).__name__}: {exc}"
        record = {"tokens": [], "engine": "tesseract", "version": version, "error": error,
                  "elapsed_ms": (time.perf_counter() - start) * 1000,
                  "preprocessing": "See preprocessing_signature; OCR failed"}
    record["document_id"] = document["id"]
    record["image_sha256"] = image_sha256
    record["preprocessing_signature"] = PREPROCESSING_SIGNATURE
    temporary = dest.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.replace(dest)
    return {"id": document["id"], "cached": False, "error": error}


def documents_to_process(partition: str = "all") -> list[dict[str, Any]]:
    sources = {"base": "data/dataset.json", "test": "data/generated/sweep/annotations.json",
               "validation": "data/generated/calibration/annotations.json"}
    docs: list[dict[str, Any]] = []
    for name, filename in sources.items():
        if partition not in {"all", name}:
            continue
        path = ROOT / filename
        if not path.exists():
            raise FileNotFoundError(f"Build the {name} population before OCR: {path}")
        docs.extend(json.loads(path.read_text(encoding="utf-8")))
    if len({d["id"] for d in docs}) != len(docs):
        raise ValueError("OCR identifiers must be unique across split populations")
    return docs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--partition", choices=["all", "base", "test", "validation"], default="all")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("Use between one and eight CPU workers")
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")
    (ROOT / "results/ocr").mkdir(parents=True, exist_ok=True)
    docs = documents_to_process(args.partition)
    version = str(pytesseract.get_tesseract_version())
    started = time.perf_counter()
    cached_count, failures = 0, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        jobs = {executor.submit(one, document, version): document["id"] for document in docs}
        for index, job in enumerate(concurrent.futures.as_completed(jobs), 1):
            result = job.result()
            cached_count += int(result["cached"])
            if result["error"]:
                failures.append(result)
            if index % 50 == 0 or index == len(docs):
                print(f"OCR {index}/{len(docs)}: {result['id']}; {cached_count} cached; {len(failures)} failed", flush=True)
    summary = {"partition": args.partition, "documents": len(docs), "cache_hits": cached_count,
               "engine": "tesseract", "version": version, "workers": args.workers, "omp_thread_limit": 1,
               "elapsed_seconds": time.perf_counter() - started, "failures": failures,
               "preprocessing_signature": PREPROCESSING_SIGNATURE}
    (ROOT / f"results/ocr-run-{args.partition}.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)
    if failures:
        sys.exit(1)
