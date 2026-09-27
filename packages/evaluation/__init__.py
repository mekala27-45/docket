"""Reference-grounded metrics, document bootstrap intervals and paired comparisons."""
from typing import Any

import numpy as np
from scipy.optimize import linear_sum_assignment

from packages.core import FIELDS, SEED, matches, normalize, required_fields


def interval(values: list[float | int | bool], *, reason: str = "No observations", bootstrap: int = 500) -> dict[str, Any]:
    if not values:
        return {"value": None, "ci": [None, None], "n": 0, "reason": reason}
    arr = np.asarray(values, dtype=float)
    rng = np.random.default_rng(SEED)
    draws = arr[rng.integers(0, len(arr), size=(bootstrap, len(arr)))].mean(axis=1)
    return {"value": float(arr.mean()), "ci": [float(np.quantile(draws, .025)), float(np.quantile(draws, .975))],
            "n": len(arr), "method": f"document bootstrap, {bootstrap} replicates, seed {SEED}, 95% percentile"}


def proportion_interval(successes: int, n: int, reason: str = "No observations") -> dict[str, Any]:
    if n == 0:
        return {"value": None, "ci": [None, None], "n": 0, "reason": reason}
    # Wilson gives non-zero uncertainty when a small set has no observed errors.
    z = 1.95996398454
    p = successes / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    spread = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** .5) / (1 + z * z / n)
    return {"value": p, "ci": [max(0, center - spread), min(1, center + spread)], "n": n,
            "method": "95% Wilson score interval"}


def fields_to_score(document: dict[str, Any]) -> list[str]:
    if document["source"] == "cord":
        return [f for f in ("subtotal", "tax", "total") if normalize(document.get(f), f)]
    return [f for f in FIELDS if normalize(document.get(f), f)]


def score_rows(predicted: list[dict[str, Any]], gold: list[dict[str, Any]]) -> float:
    if not gold:
        return 1.0 if not predicted else 0.0
    if not predicted:
        return 0.0
    weights = np.zeros((len(predicted), len(gold)))
    for i, row in enumerate(predicted):
        for j, reference in enumerate(gold):
            keys = [k for k in ("description", "quantity", "unit_price", "amount") if k in reference]
            weights[i, j] = float(all(matches(row.get(k), reference[k], k) for k in keys))
    row_index, col_index = linear_sum_assignment(-weights)
    correct = float(weights[row_index, col_index].sum())
    return 2 * correct / (len(predicted) + len(gold))


def score_document(document: dict[str, Any], extraction: dict[str, Any]) -> dict[str, Any]:
    fields = fields_to_score(document)
    values = extraction["fields"]
    results = {f: int(matches(values.get(f, {}).get("value"), document[f], f)) for f in fields}
    exact = [int(str(values.get(f, {}).get("value")) == str(document[f])) for f in fields]
    predicted = sum(values.get(f, {}).get("value") is not None for f in fields)
    tp = sum(results.values())
    denominator = predicted + len(fields)
    required = required_fields(document["type"])
    document_evaluable = bool(required) and all(normalize(document.get(f), f) for f in required)
    success = int(all(matches(values.get(f, {}).get("value"), document[f], f) for f in required)) if document_evaluable else None
    row_truth = document.get("line_items")
    row_score = score_rows(extraction.get("line_items", []), row_truth) if isinstance(row_truth, list) and (bool(row_truth) or document["source"] != "cord") else None
    return {"document_id": document["id"], "field_f1": 2 * tp / denominator if fields else None,
            "precision": (tp / predicted if predicted else 0) if fields else None,
            "recall": tp / len(fields) if fields else None,
            "exact_match": sum(exact) / len(exact) if exact else None, "document_success": success,
            "reference_fields": len(fields), "document_evaluable": document_evaluable,
            "line_item_f1": row_score,
            "fields": results}


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {key: {**interval([r[key] for r in records if r.get(key) is not None], reason="No evaluable reference labels"),
                  "population_n": len(records), "excluded_without_reference": sum(r.get(key) is None for r in records)}
            for key in ("field_f1", "precision", "recall", "exact_match", "document_success", "line_item_f1")}


def edit_distance(left: list[str] | str, right: list[str] | str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(previous[j] + 1, current[-1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def ocr_error(gold: list[dict[str, Any]], real: list[dict[str, Any]]) -> dict[str, float]:
    from packages.extract.rules import group_lines
    gold_text = " ".join(t["text"].casefold() for line in group_lines(gold) for t in line)
    real_text = " ".join(t["text"].casefold() for line in group_lines(real) for t in line)
    return {"cer": edit_distance(gold_text, real_text) / max(1, len(gold_text)),
            "wer": edit_distance(gold_text.split(), real_text.split()) / max(1, len(gold_text.split()))}


def paired_comparison(left: list[float], right: list[float]) -> dict[str, Any]:
    if len(left) != len(right) or not left:
        raise ValueError("Paired comparison requires aligned nonempty documents")
    differences = np.asarray(left) - np.asarray(right)
    rng = np.random.default_rng(SEED)
    sampled = differences[rng.integers(0, len(left), size=(1000, len(left)))].mean(axis=1)
    p_value = min(1.0, 2 * min((np.sum(sampled <= 0) + 1) / 1001, (np.sum(sampled >= 0) + 1) / 1001))
    return {"difference": interval(differences.tolist()), "p_value": float(p_value),
            "method": "paired document bootstrap sign probability; exploratory small sample"}


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    output = [0.0] * len(p_values)
    last = 1.0
    for rank in range(len(p_values), 0, -1):
        index = int(order[rank - 1])
        last = min(last, p_values[index] * len(p_values) / rank)
        output[index] = last
    return output
