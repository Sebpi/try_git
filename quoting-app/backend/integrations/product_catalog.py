"""Mock product / pricing catalog with a lightweight text-matching layer.

Real deployment swaps this for a catalog/ERP service; the matching heuristic
(exact alias hit vs. fuzzy word-overlap) is what the Product & Pricing Agent
relies on for its confidence score, and what Triage uses to decide whether a
request is unambiguous enough to call "simple".
"""
from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass

_SEED_PATH = os.path.join(os.path.dirname(__file__), "..", "seed_data", "products.json")

with open(_SEED_PATH) as f:
    PRODUCTS = json.load(f)

# category -> application engineer, used by the Routing Agent for complex quotes
ENGINEER_BY_CATEGORY = {
    "furniture": "Dana Ruiz (Furniture & Ergonomics)",
    "hardware": "Kevin Ochieng (IT Hardware)",
    "audio": "Lena Fischer (AV & Conferencing)",
}

EXACT_CONFIDENCE = 0.95
FUZZY_CONFIDENCE = 0.55
FUZZY_RATIO_THRESHOLD = 0.72

@dataclass
class MatchedLine:
    product_query_text: str
    resolved_sku: str | None
    resolved_name: str | None
    resolved_price: float | None
    currency: str | None
    quantity: int
    confidence: float
    category: str | None = None


def _all_names(product: dict) -> list[str]:
    return [product["name"].lower()] + [a.lower() for a in product.get("aliases", [])]


def _find_quantity_near(text: str, span: tuple[int, int], window_chars: int = 40) -> int:
    """Look at the preceding text for the closest quantity number, tolerating
    an adjective or two between the number and the product mention
    (e.g. "3 ergonomic office chairs")."""
    start, _ = span
    window = text[max(0, start - window_chars):start]
    nums = re.findall(r"\d+", window)
    return int(nums[-1]) if nums else 1


def match_products_in_text(text: str) -> list[MatchedLine]:
    """Scan free-form email text for catalog product mentions.

    Returns one MatchedLine per distinct product recognised (exact alias
    substring, or fuzzy word-window match). Products not mentioned at all are
    omitted -- callers combine this with an explicit "did we find *anything*"
    check to decide if the request is ambiguous.
    """
    lower = text.lower()
    matches: list[MatchedLine] = []
    seen_skus: set[str] = set()

    for product in PRODUCTS:
        for alias in _all_names(product):
            idx = lower.find(alias)
            if idx != -1:
                qty = _find_quantity_near(lower, (idx, idx + len(alias)))
                matches.append(MatchedLine(
                    product_query_text=text[idx:idx + len(alias)],
                    resolved_sku=product["sku"],
                    resolved_name=product["name"],
                    resolved_price=product["price"],
                    currency=product["currency"],
                    quantity=qty,
                    confidence=EXACT_CONFIDENCE,
                    category=product["category"],
                ))
                seen_skus.add(product["sku"])
                break  # one match per product is enough

    if matches:
        return matches

    # No exact hits -- try a fuzzy pass over 2-4 word windows so a slightly
    # misspelled or reworded request still resolves, at lower confidence.
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]*", lower)
    windows = set()
    for size in (2, 3, 4):
        for i in range(len(words) - size + 1):
            windows.add(" ".join(words[i:i + size]))

    best_by_sku: dict[str, tuple[float, str]] = {}
    for product in PRODUCTS:
        for alias in _all_names(product):
            for w in windows:
                ratio = difflib.SequenceMatcher(None, alias, w).ratio()
                if ratio >= FUZZY_RATIO_THRESHOLD:
                    prev = best_by_sku.get(product["sku"])
                    if not prev or ratio > prev[0]:
                        best_by_sku[product["sku"]] = (ratio, w)

    for product in PRODUCTS:
        hit = best_by_sku.get(product["sku"])
        if hit:
            matches.append(MatchedLine(
                product_query_text=hit[1],
                resolved_sku=product["sku"],
                resolved_name=product["name"],
                resolved_price=product["price"],
                currency=product["currency"],
                quantity=1,
                confidence=FUZZY_CONFIDENCE,
                category=product["category"],
            ))

    return matches


def engineer_for_categories(categories: list[str]) -> str:
    for c in categories:
        if c in ENGINEER_BY_CATEGORY:
            return ENGINEER_BY_CATEGORY[c]
    return "General Application Engineering Team"
