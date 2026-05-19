from __future__ import annotations

import random

from app.content_posts.rotation_memory import CTAS_HISTORY_FILE, _load_list, record_cta

CTA_POOL: list[dict[str, float | str]] = [
    {"text": "Trusted Global Transfers", "weight": 1.15},
    {"text": "Premium Currency Exchange", "weight": 1.1},
    {"text": "International Financial Services", "weight": 1.0},
    {"text": "Secure International Remittance", "weight": 1.05},
    {"text": "Modern Exchange Solutions", "weight": 0.95},
    {"text": "Fast Global Payments", "weight": 1.0},
    {"text": "Luxury Finance Services", "weight": 1.08},
    {"text": "Discover a cleaner way to manage international transfers.", "weight": 0.75},
    {"text": "Built for professionals, families, and international business needs.", "weight": 0.7},
    {"text": "A premium exchange experience for today's global lifestyle.", "weight": 0.72},
    {"text": "Secure. Professional. International.", "weight": 0.8},
]


def choose_cta(rng: random.Random | None = None) -> str:
    randomizer = rng or random.Random()
    history = _load_list(CTAS_HISTORY_FILE)
    blocked = set(history[-5:]) if history else set()
    candidates = [item for item in CTA_POOL if str(item["text"]) not in blocked]
    if not candidates:
        candidates = [item for item in CTA_POOL if str(item["text"]) not in {history[-1]}] if history else list(CTA_POOL)
    if not candidates:
        candidates = list(CTA_POOL)
    weights = [float(item.get("weight", 1.0)) for item in candidates]
    selected = randomizer.choices(candidates, weights=weights, k=1)[0]
    text = str(selected["text"])
    record_cta(text)
    return text
