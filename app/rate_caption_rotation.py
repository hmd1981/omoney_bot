from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LOGS_DIR = Path("/app/logs")
HISTORY_FILE = LOGS_DIR / "rate-caption-history.json"
TEMPLATE_COOLDOWN = 7

HASHTAG_POOL = [
    "#Omoney",
    "#صرافی_عمان",
    "#حواله_ارزی",
    "#نرخ_ارز",
    "#دلار",
    "#طلا",
    "#CurrencyExchange",
    "#MoneyTransfer",
    "#Oman",
]

CAPTION_TEMPLATES = [
    {
        "id": "live_rates_gold",
        "topic": "daily exchange rates",
        "telegram_lines": [
            "نرخ لحظه‌ای ارز و طلا با اومانی",
            "خدمات حواله، دریافت نقدی و واریز به حساب در عمان، ترکیه و امارات.",
            "",
            "انواع خدمات:",
            "• حواله ارزی",
            "• دریافت نقدی",
            "• واریز به حساب",
            "• تبدیل ارز",
        ],
        "instagram_lines": [
            "نرخ لحظه‌ای ارز و طلا با اومانی",
            "خدمات حواله، دریافت نقدی و واریز به حساب در عمان، ترکیه و امارات.",
        ],
    },
    {
        "id": "market_update",
        "topic": "live market update",
        "telegram_lines": [
            "آپدیت جدید بازار ارز و طلا",
            "اومانی؛ همراه شما در خدمات صرافی، حواله ارزی و انتقال بین‌المللی.",
            "",
            "نرخ لحظه‌ای ارز و طلا هر روز به‌صورت خودکار منتشر می‌شود.",
        ],
        "instagram_lines": [
            "آپدیت جدید بازار ارز و طلا",
            "اومانی؛ همراه شما در خدمات صرافی، حواله ارزی و انتقال بین‌المللی.",
        ],
    },
    {
        "id": "today_market_rates",
        "topic": "daily exchange rates",
        "telegram_lines": [
            "نرخ‌های امروز بازار",
            "خدمات مطمئن حواله ارزی، دریافت نقدی و واریز بانکی با اومانی.",
            "",
            "عمان • امارات • ترکیه",
        ],
        "instagram_lines": [
            "نرخ‌های امروز بازار",
            "خدمات مطمئن حواله ارزی، دریافت نقدی و واریز بانکی با اومانی.",
        ],
    },
    {
        "id": "international_finance",
        "topic": "Omoney live market",
        "telegram_lines": [
            "اومانی؛ خدمات مالی بین‌المللی",
            "نرخ لحظه‌ای ارز و طلا، همراه با خدمات حواله و تبدیل ارز.",
            "",
            "خدمات حرفه‌ای برای تجارت، سفر و خانواده.",
        ],
        "instagram_lines": [
            "اومانی؛ خدمات مالی بین‌المللی",
            "نرخ لحظه‌ای ارز و طلا، همراه با خدمات حواله و تبدیل ارز.",
        ],
    },
    {
        "id": "trusted_currency_service",
        "topic": "trusted currency service",
        "telegram_lines": [
            "اومانی؛ صرافی معتبر با سابقه حرفه‌ای",
            "نرخ لحظه‌ای ارز و طلا به‌همراه خدمات حواله ارزی مطمئن.",
            "",
            "حواله • دریافت نقدی • واریز به حساب • تبدیل ارز",
        ],
        "instagram_lines": [
            "اومانی؛ صرافی معتبر با سابقه حرفه‌ای",
            "نرخ لحظه‌ای ارز و طلا به‌همراه خدمات حواله ارزی مطمئن.",
        ],
    },
    {
        "id": "gcc_transfer_corridor",
        "topic": "Oman / UAE / Turkey transfer services",
        "telegram_lines": [
            "خدمات انتقال ارز بین عمان، امارات و ترکیه",
            "نرخ لحظه‌ای بازار با اومانی؛ همراه شما در مسیرهای تجاری و خانوادگی.",
            "",
            "حواله ارزی • دریافت نقدی • واریز بین‌المللی",
        ],
        "instagram_lines": [
            "خدمات انتقال ارز بین عمان، امارات و ترکیه",
            "نرخ لحظه‌ای بازار با اومانی.",
        ],
    },
    {
        "id": "cash_pickup_bank_deposit",
        "topic": "cash pickup and bank deposit",
        "telegram_lines": [
            "دریافت نقدی و واریز به حساب با اومانی",
            "نرخ لحظه‌ای ارز و طلا، همراه با خدمات حواله ارزی سریع و قابل پیگیری.",
            "",
            "مناسب برای تجارت، سفر و پرداخت‌های بین‌المللی.",
        ],
        "instagram_lines": [
            "دریافت نقدی و واریز به حساب با اومانی",
            "نرخ لحظه‌ای ارز و طلا و خدمات حواله ارزی.",
        ],
    },
    {
        "id": "omoney_live_market",
        "topic": "Omoney live market",
        "telegram_lines": [
            "بازار زنده ارز و طلا با اومانی",
            "آپدیت روزانه نرخ‌ها به‌همراه خدمات صرافی و انتقال بین‌المللی.",
            "",
            "اومانی • Omoney • خدمات مالی بین‌المللی",
        ],
        "instagram_lines": [
            "بازار زنده ارز و طلا با اومانی",
            "آپدیت روزانه نرخ‌ها و خدمات صرافی حرفه‌ای.",
        ],
    },
]

log = logging.getLogger("omoney-rates-bot")
_slot_templates: dict[str, str] = {}


def _ensure_logs_dir() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        payload = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _save_history(history: list[dict]) -> None:
    _ensure_logs_dir()
    HISTORY_FILE.write_text(json.dumps(history[-48:], ensure_ascii=False, indent=2), encoding="utf-8")


def _recent_template_ids() -> set[str]:
    ids: list[str] = []
    for item in _load_history():
        template_id = str(item.get("template_id", "")).strip()
        if template_id:
            ids.append(template_id)
    return set(ids[-TEMPLATE_COOLDOWN:])


def _pick_template(rng: random.Random) -> dict:
    blocked = _recent_template_ids()
    candidates = [item for item in CAPTION_TEMPLATES if item["id"] not in blocked]
    if not candidates:
        candidates = list(CAPTION_TEMPLATES)
    return rng.choice(candidates)


def _pick_hashtags(rng: random.Random) -> list[str]:
    tags = ["#Omoney"]
    remaining = [tag for tag in HASHTAG_POOL if tag not in tags]
    rng.shuffle(remaining)
    tags.extend(remaining[: rng.randint(5, min(7, len(remaining)))])
    return tags


def _format_body(lines: list[str]) -> str:
    parts: list[str] = []
    for line in lines:
        if line == "" and parts and parts[-1] == "":
            continue
        parts.append(line)
    while parts and parts[-1] == "":
        parts.pop()
    return "\n".join(parts)


def _record_template(template_id: str, slot: str) -> None:
    history = _load_history()
    history.append(
        {
            "template_id": template_id,
            "slot": slot,
            "timestamp": datetime.now(ZoneInfo("Asia/Muscat")).isoformat(),
        }
    )
    _save_history(history)


def _resolve_template(slot_key: str) -> dict:
    if slot_key not in _slot_templates:
        template = _pick_template(random.Random())
        _slot_templates[slot_key] = str(template["id"])
        _record_template(str(template["id"]), slot_key)
    template_id = _slot_templates[slot_key]
    for item in CAPTION_TEMPLATES:
        if item["id"] == template_id:
            return item
    return CAPTION_TEMPLATES[0]


def build_rate_caption(channel: str, slot: str | None = None) -> str:
    normalized_channel = channel.strip().lower()
    if normalized_channel not in {"telegram", "instagram"}:
        raise ValueError("channel must be 'telegram' or 'instagram'")
    slot_key = slot or "manual"
    template = _resolve_template(slot_key)
    rng = random.Random(f"{slot_key}:{template['id']}:{normalized_channel}")
    hashtags = _pick_hashtags(rng)
    line_key = "telegram_lines" if normalized_channel == "telegram" else "instagram_lines"
    body = _format_body(list(template[line_key]))
    if normalized_channel == "instagram":
        caption = f"{body}\n\n" + "\n".join(hashtags)
    else:
        caption = f"{body}\n\n" + " ".join(hashtags)
    log.info("rate_caption_template_id=%s", template["id"])
    log.info("rate_caption_channel=%s", normalized_channel)
    log.info("rate_caption_hashtags_count=%s", len(hashtags))
    return caption
