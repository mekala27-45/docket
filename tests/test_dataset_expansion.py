import json
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from packages.core import ROOT, read_json
from scripts import build_dataset, cache_ocr


def test_full_cord_guard_accepts_exact_official_membership() -> None:
    documents = [{"id": f"{split}-{index}", "split": split}
                 for split, count in build_dataset.CORD_COUNTS.items() for index in range(count)]
    build_dataset.validate_cord_population(documents)
    with pytest.raises(ValueError, match="full, disjoint"):
        build_dataset.validate_cord_population(documents[:-1])
    with pytest.raises(ValueError, match="full, disjoint"):
        build_dataset.validate_cord_population([])
    documents[0]["id"] = documents[1]["id"]
    with pytest.raises(ValueError, match="full, disjoint"):
        build_dataset.validate_cord_population(documents)


def test_committed_cord_has_all_shards_and_no_split_reassignment() -> None:
    documents = read_json(ROOT / "data/cord/annotations.json")
    build_dataset.validate_cord_population(documents)
    manifest = read_json(ROOT / "data/cord/source-manifest.json")
    assert len(manifest["shards"]) == 6
    assert sum(shard["rows"] for shard in manifest["shards"]) == 1000
    for document in documents:
        truth = read_json(ROOT / "data/cord/annotations" / f"{document['id']}.json")
        expected_split = {"valid": "validation"}.get(truth["meta"]["split"], truth["meta"]["split"])
        assert document["split"] == expected_split
        assert document["upstream_revision"] == build_dataset.CORD_REVISION
        assert document["official_row_index"] == truth["meta"]["image_id"]
        assert (ROOT / document["image_path"]).is_file()


def test_degradation_partitions_use_all_parents_and_five_levels() -> None:
    parents: dict[str, set[str]] = {}
    for split, folder in (("test", "sweep"), ("validation", "calibration")):
        documents = read_json(ROOT / f"data/generated/{folder}/annotations.json")
        parents[split] = {document["parent_id"] for document in documents}
        assert len(documents) == 720
        assert len(parents[split]) == 24
        assert {document["split"] for document in documents} == {split}
        populations = Counter((d["degradation"], d["level"]) for d in documents)
        assert len(populations) == 30 and set(populations.values()) == {24}
        for kind, config in build_dataset.DEGRADATIONS.items():
            assert [d["level"] for d in documents if d["parent_id"] == documents[0]["parent_id"]
                    and d["degradation"] == kind] == config["levels"]
        assert all((ROOT / document["image_path"]).is_file() for document in documents)
    assert parents["test"].isdisjoint(parents["validation"])


def test_ocr_cache_invalidates_changed_image_configuration_and_engine(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cache_ocr, "ROOT", tmp_path)
    (tmp_path / "results/ocr").mkdir(parents=True)
    image_path = tmp_path / "image.png"
    Image.new("RGB", (30, 30), "white").save(image_path)
    document = {"id": "test-page", "image_path": "image.png"}
    calls = []

    def recognize(image):
        calls.append(image.getpixel((0, 0)))
        return {"tokens": [{"text": "Total"}], "version": "test-engine"}

    monkeypatch.setattr(cache_ocr, "recognize", recognize)
    assert not cache_ocr.one(document, "test-engine")["cached"]
    assert cache_ocr.one(document, "test-engine")["cached"]
    Image.new("RGB", (30, 30), "black").save(image_path)
    assert not cache_ocr.one(document, "test-engine")["cached"]
    monkeypatch.setattr(cache_ocr, "PREPROCESSING_SIGNATURE", "new-pipeline")
    assert not cache_ocr.one(document, "test-engine")["cached"]
    assert not cache_ocr.one(document, "new-engine")["cached"]
    assert len(calls) == 4


def test_ocr_failure_is_retained_and_retried(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(cache_ocr, "ROOT", tmp_path)
    (tmp_path / "results/ocr").mkdir(parents=True)
    Image.new("RGB", (30, 30), "white").save(tmp_path / "image.png")
    calls = []

    def failure(image):
        calls.append(image.size)
        raise RuntimeError("deliberate OCR failure")

    monkeypatch.setattr(cache_ocr, "recognize", failure)
    document = {"id": "failed", "image_path": "image.png"}
    assert cache_ocr.one(document, "test-engine")["error"]
    assert cache_ocr.one(document, "test-engine")["error"]
    stored = json.loads((tmp_path / "results/ocr/failed.json").read_text())
    assert stored["tokens"] == [] and "deliberate OCR failure" in stored["error"]
    assert len(calls) == 2
