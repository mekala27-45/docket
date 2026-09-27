"""Rebuild the seeded demonstration corpus; retain original CORD split membership."""
import argparse
import io
import json
import random
import sys
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
import pyarrow.parquet as pq

from packages.core import ROOT, SEED, amount, write_json
from packages.gen import generate, degrade

CORD_MAP = {"menu.nm": "description", "menu.cnt": "quantity", "menu.unitprice": "unit_price",
            "menu.price": "amount", "menu.itemsubtotal": "amount", "sub_total.subtotal_price": "subtotal",
            "sub_total.tax_price": "tax", "total.total_price": "total"}


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "docket-reproducible-research/0.1"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.load(response)


def cord_document(row: dict[str, Any], index: int, split: str, image_bytes: bytes) -> dict[str, Any]:
    gt = json.loads(row["ground_truth"])
    width, height = gt["meta"]["image_size"]["width"], gt["meta"]["image_size"]["height"]
    tokens = []
    for line in gt["valid_line"]:
        cat = CORD_MAP.get(line["category"], "O")
        beginning = True
        for word in line["words"]:
            box = word["quad"]
            xs, ys = [box[f"x{i}"] for i in range(1, 5)], [box[f"y{i}"] for i in range(1, 5)]
            label = "O" if word.get("is_key") else cat
            tokens.append({"text": word["text"], "box": [min(xs) / width, min(ys) / height,
                            (max(xs) - min(xs)) / width, (max(ys) - min(ys)) / height],
                           "confidence": 1.0, "label": label,
                           "bio": "O" if label == "O" else ("B-" if beginning else "I-") + label,
                           "group_id": line.get("group_id")})
            if label != "O":
                beginning = False
    doc: dict[str, Any] = {"id": f"cord-{split}-{index:03d}", "type": "receipt", "source": "cord",
                           "split": split, "tokens": tokens, "currency": "IDR", "defects": [],
                           "line_items": [], "vendor": "CORD public receipt", "number": f"CORD-{index:03d}"}
    gt_parse = gt["gt_parse"]
    for key, container, source in (("total", "total", "total_price"), ("tax", "sub_total", "tax_price"),
                                    ("subtotal", "sub_total", "subtotal_price")):
        value = gt_parse.get(container, {})
        if isinstance(value, dict) and source in value:
            parsed = amount(value[source])
            if parsed is not None:
                doc[key] = float(parsed)
    menus = gt_parse.get("menu", [])
    if isinstance(menus, dict):
        menus = [menus]
    for menu in menus:
        parsed_row = {"description": menu.get("nm", "")}
        for target, sources in (("quantity", ["cnt"]), ("unit_price", ["unitprice"]),
                                ("amount", ["price", "itemsubtotal"])):
            for source in sources:
                parsed = amount(menu.get(source))
                if parsed is not None:
                    parsed_row[target] = float(parsed)
                    break
        if parsed_row.get("description"):
            doc["line_items"].append(parsed_row)
    image_path = ROOT / "data/cord/images" / f"{doc['id']}.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(image_bytes)).convert("RGB").save(image_path, quality=85)
    doc["image_path"] = image_path.relative_to(ROOT).as_posix()
    doc["image"] = f"/data/images/{doc['id']}.jpg"
    # Preserve official labels, metadata and boxes alongside the remapped demonstration schema.
    write_json(ROOT / "data/cord/annotations" / f"{doc['id']}.json", gt)
    return doc


def fetch_cord() -> list[dict[str, Any]]:
    corpus = ROOT / "data/cord/annotations.json"
    if corpus.exists():
        return json.loads(corpus.read_text(encoding="utf-8"))
    cache = ROOT / ".cache/cord-train.parquet"
    cache.parent.mkdir(exist_ok=True)
    if not cache.exists():
        urllib.request.urlretrieve("https://huggingface.co/datasets/naver-clova-ix/cord-v2/resolve/main/data/"
                                   "train-00000-of-00004-b4aaeceff1d90ecb.parquet?download=true", cache)
    rows = pq.read_table(cache).to_pylist()
    selected = sorted(random.Random(SEED).sample(range(len(rows)), 48))
    docs = [cord_document(rows[i], i, "train", rows[i]["image"]["bytes"]) for i in selected]
    for split in ("validation", "test"):
        payload = fetch_json("https://datasets-server.huggingface.co/rows?dataset=naver-clova-ix%2Fcord-v2"
                             f"&config=default&split={split}&offset=0&length=20")
        for item in payload["rows"]:
            row = item["row"]
            with urllib.request.urlopen(row["image"]["src"], timeout=60) as response:
                docs.append(cord_document(row, item["row_idx"], split, response.read()))
    license_url = "https://raw.githubusercontent.com/clovaai/cord/master/LICENSE-CC-BY"
    urllib.request.urlretrieve(license_url, ROOT / "data/cord/LICENSE-CC-BY")
    write_json(corpus, docs)
    write_json(ROOT / "data/cord/label-map.json", CORD_MAP)
    (ROOT / "data/cord/PROVENANCE.md").write_text(
        "# CORD provenance\n\nPark et al., CORD: A Consolidated Receipt Dataset for Post-OCR Parsing (2019).\n\n"
        "Source: https://github.com/clovaai/cord and https://huggingface.co/datasets/naver-clova-ix/cord-v2\n\n"
        "License: Creative Commons Attribution 4.0, copied as LICENSE-CC-BY. Images are public benchmark receipts.\n\n"
        "This is a bounded demonstration subset: 48 seeded rows from the first official training parquet shard, "
        "the first 20 validation rows and the first 20 test rows. Official split membership is preserved. "
        f"Seed: {SEED}. The training shard has {len(rows)} rows. The full benchmark is not claimed.\n\n"
        "Original annotations, quadrilaterals, semantic categories and metadata are retained per receipt. "
        "Images are re-encoded as JPEG quality 85 for repository size. All reported real OCR runs use these "
        "committed images. Boxes are normalized by the original image dimensions. CORD dot-separated "
        "thousands amounts are normalized to decimal values. Missing labels are excluded from field metrics, "
        "rather than treated as known negatives. Label mapping is label-map.json.\n\n"
        "Gold OCR contains annotated semantic lines and excludes some unannotated text. Real OCR sees the full "
        "image, so full-page CER/WER includes that annotation coverage mismatch.\n", encoding="utf-8")
    return docs


def create_sweep(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    levels = {"skew": [0, 3, 7], "blur": [0, 1, 2.5], "noise": [0, 15, 40],
              "jpeg": [95, 35, 8], "downscale": [1, .5, .22], "photograph": [0, .7, 1.5]}
    base = [d for d in docs if d["split"] == "test"][:4]
    sweep = []
    folder = ROOT / "data/generated/sweep"
    folder.mkdir(exist_ok=True)
    for doc in base:
        for kind, params in levels.items():
            for value in params:
                ident = f"{doc['id']}-{kind}-{value}"
                path = folder / f"{ident}.png"
                image = degrade(Image.open(ROOT / doc["image_path"]), kind, value)
                image.save(path, optimize=True)
                sweep.append({**doc, "id": ident, "parent_id": doc["id"], "degradation": kind,
                              "level": value, "image_path": path.relative_to(ROOT).as_posix()})
    write_json(folder / "annotations.json", sweep)
    return sweep


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-cord", action="store_true")
    args = parser.parse_args()
    generated = generate()
    print(f"Generated {len(generated)} documents", flush=True)
    cord = [] if args.skip_cord else fetch_cord()
    print(f"Ingested {len(cord)} CORD receipts", flush=True)
    sweep = create_sweep(generated)
    write_json(ROOT / "data/dataset.json", generated + cord)
    print(f"Prepared {len(sweep)} degradation observations", flush=True)
