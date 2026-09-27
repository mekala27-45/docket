"""CPU BIO token classifier with text, neighbor and normalized layout features."""
import pickle
import re
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from packages.core import AMOUNTS, FIELDS, ROOT, SEED, amount, union_box
from packages.extract.rules import candidate, field_result, group_lines

MODEL_PATH = ROOT / "results/models/token-model.pkl"


def token_features(tokens: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    features = []
    lines = group_lines(tokens)
    for line_index, line in enumerate(lines):
        for index, token in enumerate(line):
            word = token["text"].casefold()
            previous = line[index - 1]["text"].casefold() if index else "<start>"
            following = line[index + 1]["text"].casefold() if index + 1 < len(line) else "<end>"
            features.append({"text": word, "shape": re.sub(r"\d", "0", re.sub(r"[A-Za-z]", "a", word)),
                             "x": token["box"][0], "y": token["box"][1], "width": token["box"][2],
                             "height": token["box"][3], "digit_share": sum(c.isdigit() for c in word) / max(1, len(word)),
                             "is_amount": bool(re.fullmatch(r"[\d.,]+", word)), "has_hyphen": "-" in word,
                             "prefix": word[:3], "suffix": word[-3:], "left": previous, "right": following,
                             "line_keywords": " ".join(t["text"].casefold() for t in line if t["text"].isalpha()),
                             "line_position": line_index / max(1, len(lines)), "column": index / max(1, len(line)),
                             "document_type": kind})
    return features


def ordered(tokens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [token for line in group_lines(tokens) for token in line]


class TokenExtractor:
    def __init__(self) -> None:
        self.vectorizer = DictVectorizer(sparse=True)
        self.classifier = LogisticRegression(C=3.0, max_iter=300, random_state=SEED)
        self.train_ids: list[str] = []

    def fit(self, documents: list[dict[str, Any]]) -> "TokenExtractor":
        if not documents or any(d.get("split") == "test" for d in documents):
            raise ValueError("Training requires nonempty training/correction documents; test leakage is forbidden")
        features, labels = [], []
        for document in documents:
            tokens = ordered(document["tokens"])
            features.extend(token_features(tokens, document["type"]))
            previous_label = "O"
            for token in tokens:
                label = token.get("label", "O")
                bio = "O" if label == "O" else ("I-" if label == previous_label else "B-") + label
                labels.append(token.get("bio", bio))
                previous_label = label
        matrix = self.vectorizer.fit_transform(features)
        self.classifier.fit(matrix, labels)
        self.train_ids = [d["id"] for d in documents]
        return self

    def extract(self, tokens: list[dict[str, Any]], doc_type: str) -> dict[str, Any]:
        tokens = ordered(tokens)
        if not tokens:
            return {"fields": {f: field_result(f, [], "tokens") for f in FIELDS}, "line_items": [], "backend": "tokens"}
        features = token_features(tokens, doc_type)
        probabilities = self.classifier.predict_proba(self.vectorizer.transform(features))
        best = probabilities.argmax(axis=1)
        tagged = []
        for token, label_index, distribution in zip(tokens, best, probabilities, strict=True):
            bio = str(self.classifier.classes_[label_index])
            tagged.append({**token, "predicted": bio[2:] if bio != "O" else "O", "bio_prediction": bio,
                           "model_probability": float(distribution[label_index])})
        candidates: dict[str, list[dict[str, Any]]] = {f: [] for f in FIELDS}
        rows = []
        for line in group_lines(tagged):
            line_row: dict[str, Any] = {}
            for field in (*FIELDS, "description", "quantity", "unit_price", "amount"):
                chosen = [t for t in line if t["predicted"] == field]
                if not chosen:
                    continue
                value: Any = " ".join(t["text"] for t in chosen)
                score = float(np.mean([t["model_probability"] for t in chosen]))
                if field in AMOUNTS:
                    # Numeric fields choose the highest-probability numeric token in the group.
                    numeric = sorted([t for t in chosen if amount(t["text"]) is not None],
                                     key=lambda t: t["model_probability"], reverse=True)
                    if not numeric:
                        continue
                    parsed_amount = amount(numeric[0]["text"])
                    assert parsed_amount is not None
                    value = float(parsed_amount)
                    chosen = numeric[:1]
                if field in FIELDS:
                    candidates[field].append(candidate(value, chosen, score, "Predicted BIO span from CPU token classifier"))
                else:
                    line_row[field] = value
            if line_row.get("description"):
                line_row["box"] = union_box(line)
                rows.append(line_row)
        return {"fields": {f: field_result(f, values, "tokens") for f, values in candidates.items()},
                "line_items": rows, "backend": "tokens", "document_type": doc_type}

    def save(self, path: Path = MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self, protocol=5))

    @staticmethod
    def load(path: Path = MODEL_PATH) -> "TokenExtractor":
        # Only trusted repository-produced local artifacts are loaded, never upload data.
        if not path.exists():
            raise RuntimeError("Token model is not trained; run scripts/evaluate.py first")
        result = pickle.loads(path.read_bytes())
        if not isinstance(result, TokenExtractor):
            raise TypeError("Invalid local token model")
        return result
