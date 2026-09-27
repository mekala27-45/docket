import pickle

import pytest

from packages.classify import DocumentClassifier, features, letters
from packages.core import ROOT, read_json


def test_classifier_uses_text_layout_and_rejects_test_training(tmp_path):
    docs = [d for d in read_json(ROOT / "data/dataset.json") if d["split"] == "train"]
    model = DocumentClassifier().fit(docs + letters("train"))
    assert model.predict(letters("test", 1)[0]["tokens"])["type"] == "other"
    path = tmp_path / "classifier.pkl"
    model.save(path)
    assert DocumentClassifier.load(path).predict(docs[0]["tokens"])["type"] == docs[0]["type"]
    with pytest.raises(ValueError):
        model.fit(letters("test"))
    path.write_bytes(pickle.dumps(42))
    with pytest.raises(TypeError):
        DocumentClassifier.load(path)
    assert features([])["length"] == 0
