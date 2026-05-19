from __future__ import annotations

import base64
import os
import random
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.content_posts.content_themes import THEMES

WIDTH = 1080
HEIGHT = 1350
OPENAI_IMAGE_SIZE = "1024x1536"
SAFE_PAD_X = int(WIDTH * 0.12)
SAFE_PAD_Y = int(HEIGHT * 0.12)
GOLD = "#E7C16F"
GOLD_SOFT = "#D8B76D"
WHITE = "#F8F4EC"
MUTED = "#CDBF9F"
BLACK = "#050505"
ASSETS_DIR = Path("/app/assets")
FONTS_DIR = ASSETS_DIR / "fonts"

AI_PROMPT_THEMES = [
    {
        "id": "oman_luxury_exchange_office",
        "headline": "International Exchange",
        "tagline": "Premium Currency Services",
        "prompt": "a luxury private currency exchange office in Muscat Oman, refined Omani architecture, elegant black marble, gold accents, professional finance consultants and premium clients, cinematic depth of field, realistic commercial photography",
    },
    {
        "id": "muscat_skyline_finance",
        "headline": "Muscat Finance",
        "tagline": "Secure International Transfers",
        "prompt": "Muscat skyline and modern Oman business district at golden hour, premium financial lifestyle, executive client near glass architecture, luxury Gulf finance mood, cinematic realistic photography",
    },
    {
        "id": "gcc_money_transfer",
        "headline": "Global Transfers",
        "tagline": "GCC Money Movement",
        "prompt": "GCC international money transfer concept with elegant business professionals, abstract light trails suggesting secure transfers between Gulf cities, black and gold luxury finance atmosphere, realistic high-end advertising photography",
    },
    {
        "id": "turkey_remittance",
        "headline": "Istanbul Corridor",
        "tagline": "International Remittance",
        "prompt": "Istanbul finance district and premium business travel scene, Turkish remittance corridor, elegant currency exchange service, cinematic luxury commercial photo, warm gold highlights and deep black shadows",
    },
    {
        "id": "egypt_remittance",
        "headline": "Egypt Remittance",
        "tagline": "Family Support Transfers",
        "prompt": "tasteful Egyptian remittance support scene, family receiving international financial support, elegant premium office environment, warm cinematic light, luxury finance brand atmosphere, realistic photography",
    },
    {
        "id": "uae_transfer_corridor",
        "headline": "Dubai Corridor",
        "tagline": "Premium Transfer Services",
        "prompt": "Dubai financial district, luxury international transfer corridor, premium business traveler and finance consultant, Emirates style high-end atmosphere, black and gold cinematic commercial photography",
    },
    {
        "id": "cash_pickup_service",
        "headline": "Cash Pickup",
        "tagline": "Fast Secure Reliable",
        "prompt": "premium cash pickup service in a modern exchange office, professional staff handing a discreet envelope to a client, elegant luxury finance counter, shallow depth of field, realistic commercial photograph",
    },
    {
        "id": "bank_deposit_service",
        "headline": "Bank Deposit",
        "tagline": "Professional Financial Service",
        "prompt": "premium bank deposit service, elegant hands reviewing clean banking documents and digital tablet, black and gold executive desk, sophisticated international finance lifestyle, realistic cinematic advertising",
    },
    {
        "id": "gold_forex_market",
        "headline": "Gold & Forex",
        "tagline": "Luxury Market Access",
        "prompt": "luxury gold and forex market scene, elegant trading desk with gold bars and subtle blurred chart screens, premium black and gold lighting, realistic high-end commercial finance photography",
    },
    {
        "id": "airport_international_transfer",
        "headline": "Travel Transfers",
        "tagline": "International Finance Lifestyle",
        "prompt": "premium Gulf airport lounge, business traveler with luxury luggage, international transfer atmosphere, cinematic lighting, wealth and mobility, high-end realistic advertising photograph",
    },
    {
        "id": "businessman_financial_travel",
        "headline": "Business Travel",
        "tagline": "Global Currency Exchange",
        "prompt": "executive businessman in a luxury travel and finance setting, passport and premium leather bag, international currency exchange mood, cinematic Middle East business atmosphere, realistic photography",
    },
    {
        "id": "family_remittance_support",
        "headline": "Family Support",
        "tagline": "Secure Global Transfers",
        "prompt": "premium family remittance support scene, elegant family and finance professional in a warm modern interior, secure international money transfer concept, luxury lifestyle realism, cinematic commercial photography",
    },
]

AI_CAPTION_THEMES = {
    "oman_luxury_exchange_office": {"id": "ai_muscat_private_exchange", "title": "Muscat Private Exchange", "country": "Muscat", "subtitle": "Premium Currency Services"},
    "muscat_skyline_finance": {"id": "ai_muscat_finance", "title": "Muscat Finance", "country": "Muscat", "subtitle": "Secure International Transfers"},
    "gcc_money_transfer": {"id": "ai_gcc_transfers", "title": "GCC Global Transfers", "country": "GCC", "subtitle": "Money Transfer"},
    "turkey_remittance": {"id": "ai_istanbul_exchange", "title": "Istanbul Exchange Corridor", "country": "Istanbul", "subtitle": "International Remittance"},
    "egypt_remittance": {"id": "ai_family_remittance", "title": "Family Remittance Support", "country": "Global", "subtitle": "Family Support"},
    "uae_transfer_corridor": {"id": "ai_dubai_transfer", "title": "Dubai Transfer Corridor", "country": "Dubai", "subtitle": "Premium Transfer Services"},
    "cash_pickup_service": {"id": "ai_cash_pickup", "title": "Cash Pickup Services", "country": "Global", "subtitle": "Fast Secure Reliable"},
    "bank_deposit_service": {"id": "ai_bank_deposit", "title": "Bank Deposit Services", "country": "Global", "subtitle": "Professional Financial Service"},
    "gold_forex_market": {"id": "ai_gold_forex", "title": "Gold and Forex Access", "country": "Market", "subtitle": "Luxury Finance"},
    "airport_international_transfer": {"id": "ai_airport_transfer", "title": "Airport International Transfers", "country": "Global", "subtitle": "Travel Transfers"},
    "businessman_financial_travel": {"id": "ai_business_travel", "title": "Business Travel Finance", "country": "Global", "subtitle": "Global Currency Exchange"},
    "family_remittance_support": {"id": "ai_family_support", "title": "Family Support Transfers", "country": "Global", "subtitle": "Secure Global Transfers"},
}

NEGATIVE_PROMPT = (
    "No Persian text, no Arabic text, no non-English text, no readable text inside the generated scene, "
    "no fake typography, no random logos, no watermarks, no poster clutter, no overlapping text, "
    "no distorted letters, no fake Arabic, no fake Persian, no duplicate objects, no malformed hands, "
    "no extra limbs, no blurry faces, no low-quality rendering, no exchange-rate tables, no clocks, "
    "no timestamps, no phone numbers, no giant paragraphs, no crowded graphic design, no ceiling dots, "
    "no strange floating marks, no interface icons, no UI symbols, no text-like artifacts, no cropped faces, "
    "no cropped heads, no subject at image edge, no important objects near borders."
)


def _font(size: int, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont:
    if serif:
        candidates = ["Cinzel-Bold.ttf" if bold else "Cinzel-Regular.ttf", "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf"]
    else:
        candidates = ["Inter-Bold.ttf" if bold else "Inter-Regular.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for candidate in candidates:
        path = FONTS_DIR / candidate
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.truetype(candidates[-1], size)


def _size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
    return x1 - x0, y1 - y0


def openai_provider_enabled() -> bool:
    return os.getenv("CONTENT_IMAGE_PROVIDER", "").strip().lower() == "openai" and bool(os.getenv("OPENAI_API_KEY", "").strip())


def choose_ai_theme(seed: int | None = None) -> dict:
    rng = random.Random(seed or random.SystemRandom().randint(1, 10_000_000))
    return rng.choice(AI_PROMPT_THEMES)


def build_openai_prompt(theme: dict) -> str:
    return (
        "Create a realistic premium vertical luxury finance campaign image for Omoney, a currency exchange "
        "and international money transfer brand in Oman. The image must feel like an Apple luxury ad mixed "
        "with an Emirates premium campaign and a Dubai private banking visual. Visual-first composition, "
        "cinematic photography, shallow depth of field, elegant Middle East business atmosphere, black and gold "
        "finance branding through lighting and materials only. Use a clean background with large negative space "
        "for a small local brand overlay. English-only environment if any incidental signage appears, but ideally "
        "no readable signage at all. Focus on realistic professionals, families, travelers, finance consultants, "
        "Muscat, Dubai, Istanbul, international remittance, premium exchange services. Compose for Instagram "
        "vertical feed safe zones: main subject centered, face fully visible, no important content near edges, "
        "top has clean breathing space, bottom has subtle empty space, suitable for profile grid thumbnail. "
        f"Scene theme: {theme['prompt']}. {NEGATIVE_PROMPT}"
    )


def _generate_base_image(prompt: str, output_path: Path) -> None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI content image generation")
    payload = {
        "model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip() or "gpt-image-2",
        "prompt": prompt,
        "size": OPENAI_IMAGE_SIZE,
        "quality": "high",
        "output_format": "png",
        "n": 1,
    }
    response = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI image generation failed: {response.text}")
    data = response.json().get("data") or []
    if not data or not data[0].get("b64_json"):
        raise RuntimeError("OpenAI image generation response did not include b64_json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(base64.b64decode(data[0]["b64_json"]))


def _cover_output(source_path: Path) -> Image.Image:
    image = Image.open(source_path).convert("RGB")
    ratio = max(WIDTH / image.width, HEIGHT / image.height)
    resized = image.resize((int(image.width * ratio), int(image.height * ratio)), Image.Resampling.LANCZOS)
    left = (resized.width - WIDTH) // 2
    top = (resized.height - HEIGHT) // 2
    return resized.crop((left, top, left + WIDTH, top + HEIGHT)).convert("RGBA")


def _draw_right(draw: ImageDraw.ImageDraw, text: str, right: int, y: int, font: ImageFont.FreeTypeFont, fill: str) -> None:
    width, _ = _size(draw, text, font)
    draw.text((right - width, y), text, font=font, fill=fill)


def apply_brand_overlay(image: Image.Image, headline: str, tagline: str, output_path: Path) -> None:
    shade = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.rectangle((0, 0, WIDTH, SAFE_PAD_Y + 118), fill=(0, 0, 0, 126))
    sd.rounded_rectangle((SAFE_PAD_X, SAFE_PAD_Y, WIDTH - SAFE_PAD_X, HEIGHT - SAFE_PAD_Y), radius=32, outline=(231, 193, 111, 156), width=2)
    image.alpha_composite(shade)
    image = image.filter(ImageFilter.UnsharpMask(radius=1.0, percent=110, threshold=3))
    draw = ImageDraw.Draw(image)
    brand_font = _font(34, True, True)
    title_font = _font(23, True)
    tag_font = _font(19, False)
    top_y = SAFE_PAD_Y + 34
    left_x = SAFE_PAD_X + 34
    right_x = WIDTH - SAFE_PAD_X - 34
    draw.text((left_x, top_y), "OMoney", font=brand_font, fill=GOLD)
    _draw_right(draw, headline, right_x, top_y + 6, title_font, WHITE)
    _draw_right(draw, tagline, right_x, top_y + 40, tag_font, MUTED)
    draw.line((left_x, top_y + 84, right_x, top_y + 84), fill=(231, 193, 111, 142), width=1)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(output_path, "PNG")


def generate_ai_content_image(image_path: Path, timezone: str = "Asia/Muscat", seed: int | None = None) -> dict:
    theme = choose_ai_theme(seed)
    raw_path = image_path.with_name(image_path.stem + "-openai-raw.png")
    prompt = build_openai_prompt(theme)
    _generate_base_image(prompt, raw_path)
    image = _cover_output(raw_path)
    apply_brand_overlay(image, str(theme["headline"]), str(theme["tagline"]), image_path)
    mapped_theme = AI_CAPTION_THEMES.get(theme["id"], AI_CAPTION_THEMES["gcc_money_transfer"])
    return {
        "content_image_provider": "openai",
        "selected_theme": mapped_theme["id"],
        "caption_theme": mapped_theme,
        "selected_ai_prompt_theme": theme["id"],
        "selected_visual_preset": "openai_realistic_minimal_luxury",
        "headline": theme["headline"],
        "ai_image_generated": True,
        "openai_model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip() or "gpt-image-2",
        "image_path": str(image_path),
    }
