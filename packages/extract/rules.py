"""Text, proximity and alignment extraction without access to reference labels."""
import re
from typing import Any

from packages.core import FIELDS, amount, normalize, union_box

DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{4}")
NUMBER_PATTERN = re.compile(r"(?:INV|PO)[-:][\w-]+", re.IGNORECASE)


def group_lines(tokens: list[dict[str, Any]], tolerance: float = .012) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    centers: list[float] = []
    for token in sorted(tokens, key=lambda t: (t["box"][1] + t["box"][3] / 2, t["box"][0])):
        cy = token["box"][1] + token["box"][3] / 2
        if not lines or abs(cy - centers[-1]) > tolerance:
            lines.append([token])
            centers.append(cy)
        else:
            lines[-1].append(token)
            centers[-1] = sum(t["box"][1] + t["box"][3] / 2 for t in lines[-1]) / len(lines[-1])
    return [sorted(line, key=lambda t: t["box"][0]) for line in lines]


def numeric_token(token: dict[str, Any]) -> bool:
    # Accept the same locale shapes handled by amount(), including the period
    # in Rp. currency notation, while rejecting malformed grouping and labels.
    value = token["text"].strip()
    number = r"(?:\d+(?:[.,]\d{1,2})?|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,3}(?:\.\d{3})+)"
    return bool(re.fullmatch(r"(?:Rp\.?\s*|[\$€£])?[-+]?" + number, value, re.IGNORECASE)) and amount(value) is not None


def candidate(value: Any, tokens: list[dict[str, Any]], score: float, reason: str) -> dict[str, Any]:
    ocr_confidence = min((t.get("confidence", 1) for t in tokens), default=0)
    return {"value": value, "score": max(0, min(1, score * (.55 + .45 * ocr_confidence))),
            "box": union_box(tokens), "tokens": [t["text"] for t in tokens], "reason": reason}


def field_result(field: str, candidates: list[dict[str, Any]], backend: str = "rules") -> dict[str, Any]:
    ranked = sorted(candidates, key=lambda c: c["score"], reverse=True)
    chosen = ranked[0] if ranked else {"value": None, "score": 0, "box": None}
    return {"value": chosen["value"], "confidence": chosen["score"], "raw_confidence": chosen["score"],
            "box": chosen["box"], "candidates": ranked,
            "trace": [{"step": "candidates", "detail": f"{backend}: {len(ranked)} candidate(s) at floor 0.0",
                       "candidates": ranked},
                      {"step": "selection", "detail": "Highest candidate score; missing fields remain empty"},
                      {"step": "normalization", "detail": normalize(chosen["value"], field)}]}


def extract_line_items(lines: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for line in lines:
        numbers = [t for t in line if numeric_token(t)]
        if len(numbers) < 3:
            continue
        start = line.index(numbers[-3])
        description = " ".join(t["text"] for t in line[:start])
        if not description or any(word in description.casefold() for word in ("total", "tax", "date", "number")):
            continue
        qty, unit, total = [amount(t["text"]) for t in numbers[-3:]]
        if qty is None or unit is None or total is None:
            continue
        rows.append({"description": description, "quantity": float(qty), "unit_price": float(unit),
                     "amount": float(total), "box": union_box(line)})
    return rows


def extract_rules(tokens: list[dict[str, Any]], doc_type: str = "invoice") -> dict[str, Any]:
    lines = group_lines(tokens)
    candidates: dict[str, list[dict[str, Any]]] = {field: [] for field in FIELDS}
    if lines:
        header = [t for t in lines[0] if not re.fullmatch(r"invoice|purchase|order", t["text"], re.IGNORECASE)]
        if header:
            candidates["vendor"].append(candidate(" ".join(t["text"] for t in header), header, .89,
                                                       "First non-title header line"))
    for line in lines:
        line_text = " ".join(t["text"] for t in line).casefold()
        for i, token in enumerate(line):
            word = re.sub(r"[^a-z]", "", token["text"].casefold())
            if token["text"].upper() in {"USD", "EUR", "GBP", "IDR"}:
                candidates["currency"].append(candidate(token["text"].upper(), [token], .97, "ISO currency token"))
            if DATE_PATTERN.fullmatch(token["text"]):
                left = " ".join(t["text"].casefold() for t in line[:i])
                field = "due_date" if "due" in left else "date"
                candidates[field].append(candidate(token["text"], [token], .96, "Date pattern after local label"))
            if NUMBER_PATTERN.fullmatch(token["text"]):
                field = "po_number" if "reference" in line_text else "number"
                candidates[field].append(candidate(token["text"], [token], .95, "Invoice or PO identifier pattern"))
            field_name = None
            if word in {"subtotal", "subtot"}:
                field_name = "subtotal"
            elif word in {"tax", "ppn", "pajak"}:
                field_name = "tax"
            elif word in {"total", "grandtotal", "nett", "nettotal"} and "disc" not in line_text and "qty" not in token["text"].casefold():
                field_name = "total"
            if field_name:
                right = [t for t in line[i + 1:] if numeric_token(t)]
                for numeric in right:
                    parsed = amount(numeric["text"])
                    if parsed is not None:
                        position_score = .95 if numeric is right[-1] else .65
                        candidates[field_name].append(candidate(float(parsed), [numeric], position_score,
                                                                  f"Numeric token to right of {word} anchor"))
    if not candidates["total"]:
        numbers = [t for t in tokens if numeric_token(t) and t["box"][1] > .5 and t["box"][0] > .4]
        for token in numbers:
            parsed = amount(token["text"])
            if parsed is not None:
                candidates["total"].append(candidate(float(parsed), [token], .4 + .15 * token["box"][1],
                                                      "Fallback bottom-right amount; weak evidence"))
    return {"fields": {field: field_result(field, values) for field, values in candidates.items()},
            "line_items": extract_line_items(lines), "backend": "rules", "document_type": doc_type}
