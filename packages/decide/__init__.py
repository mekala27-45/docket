"""Cost selection on validation, then frozen routing on held-out test documents."""
from typing import Any

import numpy as np

from packages.core import required_fields


def document_confidence(document: dict[str, Any], extraction: dict[str, Any]) -> float:
    fields = required_fields(document.get("type", "other"))
    if not fields:
        return 0.0
    return min((extraction["fields"].get(f, {}).get("confidence", 0)
                if extraction["fields"].get(f, {}).get("value") is not None else 0) for f in fields)


def eligible(document: dict[str, Any], extraction: dict[str, Any], rules: list[dict[str, Any]],
             threshold: float) -> bool:
    required = required_fields(document.get("type", "other"))
    # Empty/unknown documents and unverified business rules fail closed.
    return (bool(required) and all(extraction["fields"].get(f, {}).get("value") is not None for f in required)
            and all(extraction["fields"].get(f, {}).get("calibration_n", 0) > 0 for f in required)
            and document_confidence(document, extraction) >= threshold and bool(rules)
            and all(rule["status"] in {"pass", "not_applicable"} for rule in rules))


def curve(records: list[dict[str, Any]], review_cost: float = 1, error_cost: float = 20) -> list[dict[str, Any]]:
    if not records:
        raise ValueError("Operating-point selection requires documents")
    points = []
    for threshold in [*np.linspace(0, 1, 21), 1.000001]:
        approved = [r for r in records if r["rules_pass"] and r["confidence"] >= threshold
                    and r.get("required_present", True)]
        errors = sum(not r["correct"] for r in approved)
        reviews = len(records) - len(approved)
        points.append({"threshold": float(threshold), "review_rate": reviews / len(records),
                       "error_rate": errors / len(approved) if approved else None,
                       "auto_approved": len(approved), "wrong_auto_approvals": errors,
                       "cost": (reviews * review_cost + errors * error_cost) / len(records)})
    return points


def choose_threshold(records: list[dict[str, Any]], split: str = "validation", review_cost: float = 1,
                     error_cost: float = 20) -> dict[str, Any]:
    if split != "validation":
        raise ValueError("Selecting an operating point on test data is forbidden")
    points = curve(records, review_cost, error_cost)
    chosen = min(points, key=lambda p: (p["cost"], p["review_rate"], -p["threshold"]))
    return {"threshold": chosen["threshold"], "chosen_on": split, "review_cost": review_cost,
            "error_cost": error_cost, "curve": points, "validation_n": len(records)}


def route(document: dict[str, Any], extraction: dict[str, Any], rules: list[dict[str, Any]],
          threshold: float) -> dict[str, Any]:
    approved = eligible(document, extraction, rules, threshold)
    confidence = document_confidence(document, extraction)
    total = extraction.get("fields", {}).get("total", {}).get("value") or 0
    try:
        risk = float(total) * (1 - confidence)
    except (TypeError, ValueError):
        risk = 0.0
    return {"status": "auto_approved" if approved else "needs_review", "risk": round(risk, 2),
            "minimum_confidence": confidence, "threshold": threshold,
            "routing_reason": "All required fields clear the validation-selected threshold and all rules pass."
                              if approved else "A required field, calibrated confidence or business check needs review."}
