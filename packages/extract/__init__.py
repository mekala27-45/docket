"""Extraction backends share an auditable field and token-box contract."""
from typing import Any

from packages.extract.rules import extract_rules


def extract(tokens: list[dict[str, Any]], doc_type: str = "invoice", backend: str = "rules",
            model: Any = None) -> dict[str, Any]:
    if backend == "rules":
        return extract_rules(tokens, doc_type)
    if backend == "tokens":
        from packages.extract.tokens import TokenExtractor
        return (model or TokenExtractor.load()).extract(tokens, doc_type)
    if backend == "vision":
        raise ValueError("The optional vision backend has not been configured or evaluated")
    raise ValueError(f"Unknown extraction backend: {backend}")
