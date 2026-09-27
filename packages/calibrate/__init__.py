"""Per-field isotonic scaling fitted only on the validation partition."""
import pickle
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression

from packages.core import ROOT

CALIBRATION_PATH = ROOT / "results/models/calibration.pkl"


def reliability(scores: list[float], outcomes: list[int], bins: int = 10) -> dict[str, Any]:
    rows = []
    ece = 0.0
    for i in range(bins):
        members = [(p, y) for p, y in zip(scores, outcomes, strict=True)
                   if i / bins <= p and (p < (i + 1) / bins or (i == bins - 1 and p == 1))]
        if not members:
            continue
        confidence = sum(p for p, _ in members) / len(members)
        accuracy = sum(y for _, y in members) / len(members)
        ece += abs(confidence - accuracy) * len(members) / max(1, len(scores))
        rows.append({"confidence": confidence, "accuracy": accuracy, "count": len(members),
                     "lower": i / bins, "upper": (i + 1) / bins})
    return {"ece": ece, "bins": rows}


class FieldCalibrator:
    def __init__(self) -> None:
        self.models: dict[str, Any] = {}
        self.population: dict[str, int] = {}
        self.fit_split = "validation"

    def fit(self, observations: list[dict[str, Any]], split: str = "validation") -> "FieldCalibrator":
        if split != "validation" or not observations:
            raise ValueError("Calibration requires nonempty held-out validation data")
        for key in sorted({f"{o['backend']}:{o['field']}" for o in observations}):
            selected = [o for o in observations if f"{o['backend']}:{o['field']}" == key]
            x, y = [o["score"] for o in selected], [o["correct"] for o in selected]
            self.population[key] = len(y)
            if len(set(x)) < 2 or len(set(y)) < 2:
                self.models[key] = float(np.mean(y))
            else:
                self.models[key] = IsotonicRegression(y_min=0, y_max=1, out_of_bounds="clip").fit(x, y)
        return self

    def predict(self, backend: str, field: str, score: float, missing: bool = False) -> float:
        if missing:
            return 0.0
        model = self.models.get(f"{backend}:{field}")
        if model is None:
            return 0.0  # Uncalibrated field types cannot silently approve an upload.
        prediction = float(model) if isinstance(model, float) else float(model.predict([score])[0])
        return max(0.0, min(1.0, prediction))

    def apply(self, extraction: dict[str, Any]) -> dict[str, Any]:
        for field, value in extraction["fields"].items():
            raw = value.get("raw_confidence", value.get("confidence", 0))
            calibrated = self.predict(extraction["backend"], field, raw, value.get("value") is None)
            value["raw_confidence"], value["confidence"] = raw, calibrated
            count = self.population.get(f"{extraction['backend']}:{field}", 0)
            value["calibration_n"] = count
            value["calibration_sentence"] = (
                f"Of 100 fields with this confidence, about {round(calibrated * 100)} were correct. "
                f"Estimated from {count} validation fields; small-sample uncertainty applies."
            ) if count else "No held-out calibration observations for this field; review required."
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
