import copy

import pytest

from packages.core import ROOT, read_json
from packages.evaluation import score_document
from packages.extract import extract
from packages.extract.rules import field_result, group_lines, numeric_token
from packages.extract.tokens import TokenExtractor, token_features
from packages.ocr import gold_words


@pytest.fixture(scope="module")
def documents():
    return read_json(ROOT / "data/dataset.json")


@pytest.mark.parametrize("index", [72, 73, 74, 75])
def test_generated_gold_recovers_four_layouts(documents, index):
    doc = documents[index]
    result = extract(gold_words(doc)["tokens"], doc["type"])
    score = score_document(doc, result)
    assert score["field_f1"] == 1
    assert score["line_item_f1"] == 1


def test_invoice_title_is_not_identifier(documents):
    doc = documents[72]
    result = extract(gold_words(doc)["tokens"])
    assert result["fields"]["number"]["value"] == doc["number"]


def test_gold_labels_do_not_leak_into_either_backend(documents):
    doc = documents[72]
    clean = gold_words(doc)["tokens"]
    poisoned = [{**t, "label": "total", "bio": "B-total"} for t in clean]
    for backend in ("rules", "tokens"):
        assert extract(clean, doc["type"], backend) == extract(poisoned, doc["type"], backend)


def test_trace_includes_all_candidates_and_selection():
    tokens = [{"text": t, "box": [.1 + i * .2, .7, .15, .02], "confidence": 1}
              for i, t in enumerate(["TOTAL", "10.00", "20.00"])]
    result = extract(tokens)["fields"]["total"]
    assert len(result["candidates"]) == 2
    assert len(result["trace"][0]["candidates"]) == 2
    assert result["value"] == 20


def test_fallback_amount_and_empty_extraction():
    tokens = [{"text": "17.00", "box": [.8, .8, .1, .03], "confidence": .8}]
    assert extract(tokens)["fields"]["total"]["value"] == 17
    assert extract([])["fields"]["total"]["value"] is None
    assert TokenExtractor.load().extract([], "other")["line_items"] == []
    assert field_result("date", [])["confidence"] == 0


def test_line_grouping_neighbor_features():
    tokens = [{"text": "Total", "box": [.1, .5, .1, .03], "confidence": 1},
              {"text": "14.00", "box": [.6, .5, .1, .03], "confidence": 1},
              {"text": "Thank", "box": [.1, .7, .1, .03], "confidence": 1}]
    assert len(group_lines(tokens)) == 2
    features = token_features(tokens, "receipt")
    assert features[1]["left"] == "total"
    assert features[1]["is_amount"]
    assert features[2]["left"] == "<start>"


def test_token_training_rejects_test_leakage(documents):
    with pytest.raises(ValueError, match="test leakage"):
        TokenExtractor().fit([documents[72]])
    with pytest.raises(ValueError):
        TokenExtractor().fit([])


def test_model_roundtrip_and_bad_artifacts(tmp_path, documents):
    model = TokenExtractor().fit([copy.deepcopy(d) for d in documents[:8]])
    path = tmp_path / "tokens.pkl"
    model.save(path)
    loaded = TokenExtractor.load(path)
    assert loaded.train_ids == model.train_ids
    assert loaded.extract(gold_words(documents[3])["tokens"], "invoice")["backend"] == "tokens"
    with pytest.raises(RuntimeError):
        TokenExtractor.load(tmp_path / "missing")


@pytest.mark.parametrize("backend", ["vision", "unknown"])
def test_unavailable_backend_is_explicit(backend):
    with pytest.raises(ValueError):
        extract([], backend=backend)


def test_missing_money_is_not_published_as_zero():
    from packages.pipeline import process_document
    document = process_document({"id": "unreadable", "type": "other", "source": "upload", "tokens": []})
    assert document["total"] is None
    assert document["subtotal"] is None
    assert document["tax"] is None
    assert document["status"] == "needs_review"


@pytest.mark.parametrize("text", ["Rp.118.000", "rp118.000", "RP. 1.234.000", "$1,234.56", "€12,50", "-25.40"])
def test_numeric_token_accepts_supported_currency_prefixes(text):
    assert numeric_token({"text": text})


@pytest.mark.parametrize("text", ["Rp.", "Rp.12..3", "12,,", "1,2,3", "Total118.000", "INV-123", "2026-09-27", "NaN"])
def test_numeric_token_refuses_malformed_or_nonmonetary_values(text):
    assert not numeric_token({"text": text})


def test_rules_extract_total_with_attached_rupiah_prefix():
    tokens = [{"text": text, "box": [.1 + index * .4, .7, .3, .03], "confidence": 1}
              for index, text in enumerate(["Total", "Rp.118.000"])]
    assert extract(tokens)["fields"]["total"]["value"] == 118000
