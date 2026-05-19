from __future__ import annotations

import random

from app.content_posts.composition_profiles import COMPOSITION_PROFILES, PROFILE_IDS
from app.content_posts.rotation_memory import pick_axis, pick_composition, record_composition, record_rotation_bundle

SCENES = [
    "private exchange lounge",
    "executive airport lounge",
    "Muscat waterfront boardroom",
    "Dubai financial district terrace",
    "premium family consultation room",
    "gold and forex trading desk",
    "modern remittance service counter",
    "Gulf business hotel lobby",
]

BUSINESS_ENVIRONMENTS = [
    "boutique currency exchange office",
    "international remittance center",
    "private banking consultation suite",
    "corporate treasury meeting space",
    "luxury travel finance desk",
    "family remittance support lounge",
]

COUNTRY_FOCUS = [
    "Oman and Muscat",
    "UAE and Dubai",
    "Turkey and Istanbul",
    "Egypt remittance corridor",
    "GCC regional business",
    "global international transfers",
]

LIGHTING_STYLES = [
    "cinematic golden hour",
    "soft window daylight with gold accents",
    "moody low-key finance lighting",
    "clean high-end commercial key light",
    "warm hospitality finance glow",
]

CAMERA_ANGLES = [
    "eye-level medium shot",
    "slight low-angle prestige framing",
    "three-quarter environmental portrait",
    "shallow depth editorial close-up",
    "wide establishing business scene",
]

FINANCE_MOODS = [
    "trusted and secure",
    "premium and aspirational",
    "professional and efficient",
    "warm family support",
    "executive global mobility",
]

HASHTAG_ROTATION_GROUPS = [
    ["#Omoney", "#CurrencyExchange", "#GlobalTransfers"],
    ["#Muscat", "#OmanBusiness", "#GCCFinance"],
    ["#Dubai", "#InternationalFinance", "#LuxuryFinance"],
    ["#Istanbul", "#Remittance", "#MoneyTransfer"],
    ["#PremiumFinance", "#SecureTransfers", "#BusinessTravel"],
]


def build_rotation_bundle(rng: random.Random | None = None) -> dict[str, str]:
    randomizer = rng or random.Random()
    composition_id = pick_composition(PROFILE_IDS, lambda item: item, randomizer)
    profile = COMPOSITION_PROFILES[composition_id]
    bundle = {
        "scene": pick_axis("scene", SCENES, randomizer),
        "business_environment": pick_axis("business_environment", BUSINESS_ENVIRONMENTS, randomizer),
        "country_focus": pick_axis("country_focus", COUNTRY_FOCUS, randomizer),
        "lighting_style": pick_axis("lighting_style", LIGHTING_STYLES, randomizer),
        "camera_angle": pick_axis("camera_angle", CAMERA_ANGLES, randomizer),
        "finance_mood": pick_axis("finance_mood", FINANCE_MOODS, randomizer),
        "composition_profile": composition_id,
        "composition_label": str(profile.get("label", composition_id)),
    }
    record_composition(composition_id)
    record_rotation_bundle(
        {
            "scene": bundle["scene"],
            "business_environment": bundle["business_environment"],
            "country_focus": bundle["country_focus"],
            "lighting_style": bundle["lighting_style"],
            "camera_angle": bundle["camera_angle"],
            "finance_mood": bundle["finance_mood"],
        }
    )
    return bundle


def rotation_prompt_suffix(bundle: dict[str, str]) -> str:
    profile = COMPOSITION_PROFILES.get(bundle.get("composition_profile", ""), {})
    return (
        f"Scene: {bundle.get('scene', '')}. "
        f"Environment: {bundle.get('business_environment', '')}. "
        f"Country focus: {bundle.get('country_focus', '')}. "
        f"Lighting: {bundle.get('lighting_style', '')}. "
        f"Camera: {bundle.get('camera_angle', '')}. "
        f"Mood: {bundle.get('finance_mood', '')}. "
        f"Composition direction: {profile.get('framing', '')}. "
        f"Lighting mood: {profile.get('lighting_mood', '')}. "
        f"Visual balance: {profile.get('visual_balance', '')}."
    )


def pick_hashtag_set(rng: random.Random) -> list[str]:
    group = rng.choice(HASHTAG_ROTATION_GROUPS)
    extras = ["#Omoney"]
    for tag in group:
        if tag not in extras:
            extras.append(tag)
    return extras
