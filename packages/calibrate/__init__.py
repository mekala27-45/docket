"""Per-field isotonic scaling fitted only on the validation partition."""
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression

from packages.core import ROOT, SEED
from packages.evaluation import proportion_interval

CALIBRATION_PATH = ROOT / "results/models/calibration.pkl"


def reliability(scores: list[float], outcomes: list[int], bins: int = 10,
                groups: list[str] | None = None) -> dict[str, Any]:
    if len(scores) != len(outcomes) or (groups is not None and len(groups) != len(scores)):
        raise ValueError("Reliability scores, outcomes and parent IDs must align")
    if bins < 1 or any(not 0 <= p <= 1 for p in scores):
        raise ValueError("Reliability requires probabilities and positive bin count")
    rows = []
    ece = 0.0
    for i in range(bins):
        indices = [j for j, p in enumerate(scores)
                   if i / bins <= p and (p < (i + 1) / bins or (i == bins - 1 and p == 1))]
        members = [(scores[j], outcomes[j]) for j in indices]
        if not members:
            continue
        confidence = sum(p for p, _ in members) / len(members)
        accuracy = sum(y for _, y in members) / len(members)
        ece += abs(confidence - accuracy) * len(members) / max(1, len(scores))
        uncertainty = proportion_interval(sum(y for _, y in members), len(members))
        independent = len(members)
        if groups is not None:
            parents = sorted({groups[j] for j in indices})
            independent = len(parents)
            counts = np.asarray([sum(groups[j] == parent for j in indices) for parent in parents])
            totals = np.asarray([sum(outcomes[j] for j in indices if groups[j] == parent) for parent in parents])
            rng = np.random.default_rng(SEED)
            draws = rng.integers(0, len(parents), size=(500, len(parents)))
            rates = totals[draws].sum(axis=1) / counts[draws].sum(axis=1)
            uncertainty = {"ci": [float(np.quantile(rates, .025)), float(np.quantile(rates, .975))],
                           "method": "95% parent-document cluster bootstrap, 500 replicates"}
            if accuracy in (0, 1):
                uncertainty = proportion_interval(round(accuracy * independent), independent)
                uncertainty["method"] = "95% Wilson bound using distinct parent-page count for an all-equal bin"
        rows.append({"confidence": confidence, "accuracy": accuracy, "count": len(members),
                     "independent_documents": independent, "ci": uncertainty["ci"],
                     "interval_method": uncertainty["method"], "lower": i / bins, "upper": (i + 1) / bins})
    return {"ece": ece, "bins": rows}


class FieldCalibrator:
    def __init__(self) -> None:
        self.models: dict[str, Any] = {}
        self.population: dict[str, int] = {}
        self.parents: dict[str, int] = {}
        self.fit_split = "validation"

    def fit(self, observations: list[dict[str, Any]], split: str = "validation") -> "FieldCalibrator":
        if split != "validation" or not observations or any(o.get("split", "validation") != "validation" for o in observations):
            raise ValueError("Calibration requires nonempty held-out validation data")
        if any(not 0 <= o["score"] <= 1 or o["correct"] not in (0, 1) for o in observations):
            raise ValueError("Calibration requires probabilities and binary reference outcomes")
        def key_for(row: dict[str, Any]) -> str:
            return f"{row['backend']}:{row.get('population', 'all')}:{row['field']}"

        self.models.clear()
        self.population.clear()
        self.parents.clear()
        for key in sorted({key_for(o) for o in observations}):
            selected = [o for o in observations if key_for(o) == key]
            x, y = [o["score"] for o in selected], [o["correct"] for o in selected]
            self.population[key] = len(y)
            self.parents[key] = len({o.get("parent_id", str(i)) for i, o in enumerate(selected)})
            if len(set(x)) < 2 or len(set(y)) < 2:
                self.models[key] = float(np.mean(y))
            else:
                self.models[key] = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(x, y)
        return self

    def predict(self, backend: str, field: str, score: float, missing: bool = False,
                population: str = "all") -> float:
        if missing:
            return 0.0
        model = self.models.get(f"{backend}:{population}:{field}", self.models.get(f"{backend}:all:{field}"))
        if model is None:
            return 0.0  # Uncalibrated field types cannot silently approve an upload.
        prediction = float(model) if isinstance(model, float) else float(model.predict([score])[0])
        return max(0.0, min(1.0, prediction))

    def apply(self, extraction: dict[str, Any]) -> dict[str, Any]:
        for field, value in extraction["fields"].items():
            population = "cord" if extraction.get("document_type") == "receipt" else "generated"
            raw = value.get("raw_confidence", value.get("confidence", 0))
            calibrated = self.predict(extraction["backend"], field, raw, value.get("value") is None, population)
            value["raw_confidence"], value["confidence"] = raw, calibrated
            key = f"{extraction['backend']}:{population}:{field}"
            if key not in self.population:
                key = f"{extraction['backend']}:all:{field}"
            count = self.population.get(key, 0)
            parents = getattr(self, "parents", {}).get(key, count)
            if extraction.get('document_type') == 'receipt' and field not in {'subtotal', 'tax', 'total'}:
                # CORD has no header truth for these invoice fields. Do not
                # transfer a generated-header calibration claim to a receipt.
                count = 0
                value['confidence'] = calibrated = 0.0
            value["calibration_n"] = count
            value["calibration_documents"] = parents if count else 0
            value["calibration_population"] = population
            value["calibration_sentence"] = (
                f"Of 100 fields with this confidence, about {round(calibrated * 100)} were correct. "
                f"Estimated from {count} validation fields from {parents} distinct parent pages. "
                + ("Population: generated pages including controlled degradations; variants share source documents."
                   if population == "generated" else "Population: public CORD receipt amount fields.")
            ) if count else "No held-out calibration observations for this field and document population; review required."
            value["trace"].append({"step": "calibration", "detail": value["calibration_sentence"],
                                   "raw": raw, "calibrated": calibrated, "split": self.fit_split})
        return extraction

    def save(self, path: Path = CALIBRATION_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(self, protocol=5))

    @staticmethod
    def load(path: Path = CALIBRATION_PATH) -> "FieldCalibrator":
        if not path.exists():
            return FieldCalibrator()
        result = pickle.loads(path.read_bytes())
        if not isinstance(result, FieldCalibrator):
            raise TypeError("Invalid local calibration model")
        return result
