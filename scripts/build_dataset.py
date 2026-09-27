"""Rebuild the seeded demonstration corpus; retain original CORD split membership."""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pyarrow.parquet as pq
from PIL import Image

from packages.core import ROOT, SEED, amount, write_json
from packages.gen import degrade, generate

CORD_MAP = {"menu.nm": "description", "menu.cnt": "quantity", "menu.unitprice": "unit_price",
            "menu.price": "amount", "menu.itemsubtotal": "amount", "sub_total.subtotal_price": "subtotal",
            "sub_total.tax_price": "tax", "total.total_price": "total"}
CORD_REVISION = "7f0115a4b758a71d6473b8d085751692da2fef98"
CORD_SHARDS = {
    "train": ["train-00000-of-00004-b4aaeceff1d90ecb.parquet", "train-00001-of-00004-7dbbe248962764c5.parquet",
              "train-00002-of-00004-688fe1305a55e5cc.parquet", "train-00003-of-00004-2d0cd200555ed7fd.parquet"],
    "validation": ["validation-00000-of-00001-cc3c5779fe22e8ca.parquet"],
    "test": ["test-00000-of-00001-9c204eb3f4e11791.parquet"],
}
CORD_COUNTS = {"train": 800, "validation": 100, "test": 100}
DEGRADATIONS: dict[str, dict[str, Any]] = {
    "skew": {"levels": [0, 1.5, 3, 5, 7], "unit": "degrees", "severe_direction": "increasing"},
    "blur": {"levels": [0, .5, 1, 1.75, 2.5], "unit": "Gaussian radius in pixels", "severe_direction": "increasing"},
    "noise": {"levels": [0, 10, 20, 30, 40], "unit": "Gaussian RGB standard deviation", "severe_direction": "increasing"},
    "jpeg": {"levels": [95, 60, 35, 18, 8], "unit": "JPEG quality", "severe_direction": "decreasing"},
    "downscale": {"levels": [1, .75, .5, .35, .22], "unit": "resolution factor", "severe_direction": "decreasing"},
    "photograph": {"levels": [0, .35, .7, 1.1, 1.5], "unit": "perspective and lighting severity", "severe_direction": "increasing"},
}


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


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download_shard(name: str) -> Path:
    cache = ROOT / ".cache/cord" / name
    cache.parent.mkdir(parents=True, exist_ok=True)
    legacy = ROOT / ".cache/cord-train.parquet"
    if name == CORD_SHARDS["train"][0] and not cache.exists() and legacy.exists():
        # Reuse the previously downloaded first shard without duplicating half a GB.
        os.link(legacy, cache)
    if cache.exists():
        pq.ParquetFile(cache)  # Refuse a corrupt or incomplete download.
        return cache
    url = f"https://huggingface.co/datasets/naver-clova-ix/cord-v2/resolve/{CORD_REVISION}/data/{name}?download=true"
    temporary = cache.with_suffix(".part")
    for attempt in range(3):
        try:
            urllib.request.urlretrieve(url, temporary)
            pq.ParquetFile(temporary)
            temporary.replace(cache)
            print(f"Downloaded {name}", flush=True)
            return cache
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("Download retry loop exhausted")


def validate_cord_population(docs: list[dict[str, Any]]) -> None:
    actual = {split: sum(d["split"] == split for d in docs) for split in CORD_COUNTS}
    if actual != CORD_COUNTS or len({d["id"] for d in docs}) != 1000:
        raise ValueError(f"CORD requires the full, disjoint official splits: {actual}")


def fetch_cord() -> list[dict[str, Any]]:
    corpus = ROOT / "data/cord/annotations.json"
    if corpus.exists():
        current = json.loads(corpus.read_text(encoding="utf-8"))
        if len(current) == 1000 and all(d.get("upstream_revision") == CORD_REVISION for d in current):
            validate_cord_population(current)
            return current
    names = [name for shards in CORD_SHARDS.values() for name in shards]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        cached = dict(zip(names, pool.map(download_shard, names), strict=True))
    docs: list[dict[str, Any]] = []
    source_manifest = []
    for split, names_in_split in CORD_SHARDS.items():
        offset = 0
        for name in names_in_split:
            parquet = pq.ParquetFile(cached[name])
            source_manifest.append({"split": split, "filename": name, "rows": parquet.metadata.num_rows,
                                    "sha256": sha256(cached[name]), "bytes": cached[name].stat().st_size})
            shard_index = 0
            # Streaming batches avoid materializing all embedded image bytes at once.
            for batch in parquet.iter_batches(batch_size=8):
                for row in batch.to_pylist():
                    gt = json.loads(row["ground_truth"])
                    metadata_split = {"valid": "validation"}.get(gt["meta"]["split"], gt["meta"]["split"])
                    if metadata_split != split:
                        raise ValueError(f"Upstream split mismatch in {name} at {shard_index}")
                    doc = cord_document(row, offset + shard_index, split, row["image"]["bytes"])
                    doc.update({"upstream_revision": CORD_REVISION, "upstream_shard": name,
                                "upstream_row": shard_index, "official_row_index": offset + shard_index})
                    docs.append(doc)
                    shard_index += 1
            offset += shard_index
            print(f"Ingested {split}: {offset}/{CORD_COUNTS[split]}", flush=True)
    validate_cord_population(docs)
    license_url = "https://raw.githubusercontent.com/clovaai/cord/master/LICENSE-CC-BY"
    urllib.request.urlretrieve(license_url, ROOT / "data/cord/LICENSE-CC-BY")
    write_json(corpus, docs)
    write_json(ROOT / "data/cord/label-map.json", CORD_MAP)
    write_json(ROOT / "data/cord/source-manifest.json", {"revision": CORD_REVISION, "splits": CORD_COUNTS,
                                                        "shards": source_manifest})
    (ROOT / "data/cord/PROVENANCE.md").write_text(
        "# CORD provenance\n\nPark et al., CORD: A Consolidated Receipt Dataset for Post-OCR Parsing (2019).\n\n"
        "Source: https://github.com/clovaai/cord and https://huggingface.co/datasets/naver-clova-ix/cord-v2\n\n"
        "License: Creative Commons Attribution 4.0, copied as LICENSE-CC-BY. Images are public benchmark receipts.\n\n"
        "All official CORD v2 rows are included: 800 training, 100 validation and 100 test receipts. "
        "Every row from all four training shards and the validation/test shards is retained, in upstream order. "
        "Official split membership is preserved and verified against each annotation's metadata (the original `valid` alias maps to `validation`); no sampling or repartitioning occurs. "
        f"Pinned dataset revision: `{CORD_REVISION}`. Each original parquet's SHA-256 and row count is in source-manifest.json.\n\n"
        "Original annotations, quadrilaterals, semantic categories and metadata are retained per receipt. "
        "Images are re-encoded as JPEG quality 85 for repository size. All reported real OCR runs use these "
        "committed images. Boxes are normalized by the original image dimensions. CORD dot-separated "
        "thousands amounts are normalized to decimal values. Missing labels are excluded from field metrics, "
        "rather than treated as known negatives. Label mapping is label-map.json.\n\n"
        "Gold OCR contains annotated semantic lines and excludes some unannotated text. Real OCR sees the full "
        "image, so full-page CER/WER includes that annotation coverage mismatch.\n", encoding="utf-8")
    return docs


def create_sweep(docs: list[dict[str, Any]], split: str = "test") -> list[dict[str, Any]]:
    if split not in {"validation", "test"}:
        raise ValueError("Degradation partitions must be held-out validation or test")
    base = [d for d in docs if d["split"] == split]
    sweep = []
    folder = ROOT / "data/generated" / ("sweep" if split == "test" else "calibration")
    folder.mkdir(exist_ok=True)
    for doc in base:
        with Image.open(ROOT / doc["image_path"]) as source:
            original = source.convert("RGB")
        for kind, config in DEGRADATIONS.items():
            for level_index, value in enumerate(config["levels"]):
                ident = f"{doc['id']}-{kind}-{value}"
                path = folder / f"{ident}.png"
                image = degrade(original, kind, value)
                image.save(path, compress_level=6)
                sweep.append({**doc, "id": ident, "parent_id": doc["id"], "degradation": kind,
                              "level": value, "level_index": level_index, "degradation_unit": config["unit"],
                              "image_path": path.relative_to(ROOT).as_posix(),
                              "image": f"/data/images/{ident}.png", "degradation_seed": SEED})
        print(f"Degraded {split} parent {doc['id']}: {len(sweep)} observations", flush=True)
    write_json(folder / "annotations.json", sweep)
    write_json(folder / "config.json", {"split": split, "parent_count": len(base), "observation_count": len(sweep),
                                       "seed": SEED, "parameters": DEGRADATIONS,
                                       "sampling_unit": "parent_id; level observations share document truth",
                                       "parameters_selected_before_expanded_test_evaluation": True})
    return sweep


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-cord", action="store_true")
    parser.add_argument("--cord-only", action="store_true")
    parser.add_argument("--degradation-only", action="store_true")
    args = parser.parse_args()
    if args.cord_only and args.degradation_only:
        parser.error("Choose at most one of --cord-only and --degradation-only")
    generated_file = ROOT / "data/generated/annotations.json"
    generated = json.loads(generated_file.read_text(encoding="utf-8")) if generated_file.exists() else generate()
    print(f"Generated {len(generated)} documents", flush=True)
    if not args.degradation_only:
        cord = [] if args.skip_cord else fetch_cord()
        print(f"Ingested {len(cord)} CORD receipts", flush=True)
        write_json(ROOT / "data/dataset.json", generated + cord)
    if not args.cord_only:
        sweep = create_sweep(generated)
        calibration = create_sweep(generated, "validation")
        print(f"Prepared {len(sweep)} test and {len(calibration)} validation degradation observations", flush=True)
