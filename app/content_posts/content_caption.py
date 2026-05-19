from __future__ import annotations

import random

from app.content_posts.content_rotation import pick_hashtag_set
from app.content_posts.cta_rotation import choose_cta

CAPTION_VARIANTS = {
    "muscat": [
        "Premium financial services for global transfers from Oman.",
        "Move money with confidence through a refined international exchange experience.",
    ],
    "dubai": [
        "Connecting business, travel, and international finance across the Gulf.",
        "Designed for modern entrepreneurs moving between Oman, Dubai, and global markets.",
    ],
    "istanbul": [
        "A refined exchange experience for the Oman-Turkey transfer corridor.",
        "International remittance for business, travel, and family support.",
    ],
    "family": [
        "Reliable transfer support for families, business owners, and international lifestyles.",
        "Secure global transfers with a premium service mindset.",
    ],
    "default": [
        "Luxury currency exchange and international transfer services for a connected world.",
        "Premium currency services for global movement, business, and lifestyle.",
    ],
}

HASHTAG_POOL = [
    "#Omoney",
    "#CurrencyExchange",
    "#GlobalTransfers",
    "#Muscat",
    "#Dubai",
    "#Istanbul",
    "#MoneyTransfer",
    "#InternationalFinance",
    "#LuxuryFinance",
    "#OmanBusiness",
    "#GCCFinance",
    "#Remittance",
]


def _caption_key(theme: dict) -> str:
    value = " ".join(str(theme.get(key, "")).lower() for key in ("id", "title", "country", "subtitle"))
    if "muscat" in value or "oman" in value:
        return "muscat"
    if "dubai" in value or "uae" in value:
        return "dubai"
    if "istanbul" in value or "turkey" in value:
        return "istanbul"
    if "family" in value or "egypt" in value:
        return "family"
    return "default"


def build_caption(theme: dict, seed: int | None = None, metadata: dict | None = None) -> str:
    rng = random.Random(seed or random.SystemRandom().randint(1, 10_000_000))
    key = _caption_key(theme)
    opener = rng.choice(CAPTION_VARIANTS.get(key, CAPTION_VARIANTS["default"]))
    if metadata and metadata.get("selected_cta"):
        cta = str(metadata["selected_cta"])
    else:
        cta = choose_cta(rng)
    tags = pick_hashtag_set(rng)
    remaining = [tag for tag in HASHTAG_POOL if tag not in tags]
    rng.shuffle(remaining)
    tags.extend(remaining[: max(0, 8 - len(tags))])
    return "\n\n".join([opener, cta, " ".join(tags)])
