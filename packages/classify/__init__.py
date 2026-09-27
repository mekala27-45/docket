"""CPU text and layout classifier; no pretrained document model."""
import pickle
from pathlib import Path
from typing import Any

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from packages.core import ROOT, SEED

CLASSIFIER_PATH = ROOT / "results/models/document-classifier.pkl"
LABELS = ["invoice", "purchase_order", "receipt", "other"]


def features(tokens: list[dict[str, Any]]) -> dict[str, Any]:
    words = [t["text"].casefold() for t in tokens]
    joined = " ".join(words)
    output: dict[str, Any] = {"length": len(words) / 100, "numeric_share": sum(w.isdigit() for w in words) / max(1, len(words)),
                              "top_share": sum(t["box"][1] < .2 for t in tokens) / max(1, len(tokens))}
    for phrase in ["invoice", "purchase order", "bill to", "total", "qty", "thank", "dear", "meeting", "receipt"]:
        output[f"has:{phrase}"] = phrase in joined
    for word in words:
        output[f"word:{word}"] = True
    return output


class DocumentClassifier:
    def __init__(self) -> None:
        self.vectorizer = DictVectorizer()
        self.model = LogisticRegression(max_iter=200, random_state=SEED)

    def fit(self, documents: list[dict[str, Any]]) -> "DocumentClassifier":
        if any(d.get("split") == "test" for d in documents):
            raise ValueError("Test data cannot train the classifier")
        self.model.fit(self.vectorizer.fit_transform([features(d["tokens"]) for d in documents]),
                       [d["type"] for d in documents])
        return self

    def predict(self, tokens: list[dict[str, Any]]) -> dict[str, Any]:
        probabilities = self.model.predict_proba(self.vectorizer.transform([features(tokens)]))[0]
        index = int(probabilities.argmax())
        return {"type": str(self.model.classes_[index]), "score": float(probabilities[index]),
                "backend": "linear-text-layout", "score_kind": "uncalibrated classifier probability"}

    def save(self, path: Path = CLASSIFIER_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self, protocol=5))

    @staticmethod
    def load(path: Path = CLASSIFIER_PATH) -> "DocumentClassifier":
        result = pickle.loads(path.read_bytes())
        if not isinstance(result, DocumentClassifier):
            raise TypeError("Invalid local document classifier")
        return result


def letters(split: str, count: int = 12) -> list[dict[str, Any]]:
    templates = ["Dear team please attend the planning meeting on Monday regards office manager",
                 "Internal memorandum maintenance schedule for the studio equipment thanks team",
                 "Dear colleague this letter confirms our meeting agenda and project discussion"]
    docs = []
    for i in range(count):
        sentence = templates[i % len(templates)] + f" Reference {split} {i}"
        docs.append({"id": f"letter-{split}-{i}", "type": "other", "split": split,
                     "tokens": [{"text": w, "box": [.08 + (j % 7) * .10, .2 + (j // 7) * .04, .08, .02],
                                 "confidence": 1, "label": "O"} for j, w in enumerate(sentence.split())]})
    return docs
