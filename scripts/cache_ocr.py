"""Run real Tesseract once per committed image, in native Python or the OCR container."""
import concurrent.futures
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from packages.ocr import recognize

ROOT = Path(__file__).resolve().parents[1]


def one(document):
    dest = ROOT / "results/ocr" / f"{document['id']}.json"
    if dest.exists():
        return document["id"]
    record = recognize(Image.open(ROOT / document["image_path"]))
    record["document_id"] = document["id"]
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return document["id"]


if __name__ == "__main__":
    (ROOT / "results/ocr").mkdir(parents=True, exist_ok=True)
    docs = json.loads((ROOT / "data/dataset.json").read_text(encoding="utf-8"))
    docs += json.loads((ROOT / "data/generated/sweep/annotations.json").read_text(encoding="utf-8"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for index, result in enumerate(executor.map(one, docs)):
            if index % 20 == 0:
                print(f"OCR {index + 1}/{len(docs)}: {result}", flush=True)
