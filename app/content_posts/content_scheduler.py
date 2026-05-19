from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.content_posts.ai_image_generator import generate_ai_content_image, openai_provider_enabled
from app.content_posts.content_caption import build_caption
from app.content_posts.content_generator import generate_content_image
from app.content_posts.content_themes import THEMES


CONTENT_LOG_FILE = Path("/app/logs/content-posts.jsonl")
CONTENT_OUTPUT_DIR = Path("/app/output/content")


def content_enabled() -> bool:
    return os.getenv("CONTENT_ENABLED", "").strip().lower() == "true"


def content_publish_times() -> list[str]:
    configured = os.getenv("CONTENT_PUBLISH_TIMES", "10:00,17:00,22:00").strip()
    return [item.strip() for item in configured.split(",") if item.strip()]


def content_slot(timezone: str, scheduled_time: str | None = None) -> str:
    now = datetime.now(ZoneInfo(timezone))
    return now.strftime("%Y-%m-%dT") + (scheduled_time or now.strftime("%H:%M"))


def append_content_record(record: dict) -> None:
    CONTENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONTENT_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def load_content_records() -> list[dict]:
    if not CONTENT_LOG_FILE.exists():
        return []
    records: list[dict] = []
    for line in CONTENT_LOG_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def content_slot_completed(slot: str) -> bool:
    for record in load_content_records():
        if record.get("scheduled_slot") == slot and record.get("telegram_sent") and record.get("instagram_published"):
            return True
    return False


def next_content_run(timezone: str) -> str:
    now = datetime.now(ZoneInfo(timezone))
    candidates: list[datetime] = []
    for item in content_publish_times():
        hour_text, minute_text = item.split(":", 1)
        candidate = now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        candidates.append(candidate)
    return min(candidates).isoformat() if candidates else ""


def last_content_successes() -> dict:
    result = {"telegram": "", "instagram": ""}
    for record in load_content_records():
        slot = str(record.get("scheduled_slot", ""))
        if record.get("telegram_sent"):
            result["telegram"] = slot
        if record.get("instagram_published"):
            result["instagram"] = slot
    return result


def generate_content_preview(timezone: str) -> tuple[Path, dict, str]:
    CONTENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = CONTENT_OUTPUT_DIR / "content-preview.png"
    if openai_provider_enabled():
        metadata = generate_ai_content_image(image_path=image_path, timezone=timezone)
    else:
        metadata = generate_content_image(image_path=image_path, history_path=CONTENT_LOG_FILE, timezone=timezone)
    theme = metadata.get("caption_theme") or next((item for item in THEMES if item["id"] == metadata["selected_theme"]), THEMES[0])
    caption = build_caption(theme)
    return image_path, metadata, caption


def generate_ai_content_preview(timezone: str) -> tuple[Path, dict, str]:
    CONTENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = CONTENT_OUTPUT_DIR / "content-ai-preview.png"
    metadata = generate_ai_content_image(image_path=image_path, timezone=timezone)
    theme = metadata.get("caption_theme") or next((item for item in THEMES if item["id"] == metadata["selected_theme"]), THEMES[0])
    caption = build_caption(theme)
    return image_path, metadata, caption


def publish_content_post(
    *,
    timezone: str,
    scheduled_time: str | None,
    send_telegram,
    publish_instagram,
    upload_image,
    verify_public_url,
) -> dict:
    slot = content_slot(timezone, scheduled_time)
    record = {
        "scheduled_slot": slot,
        "timestamp": datetime.now(ZoneInfo(timezone)).isoformat(),
        "content_generated": False,
        "r2_uploaded": False,
        "telegram_sent": False,
        "instagram_published": False,
        "errors": {},
    }
    if content_slot_completed(slot):
        record["duplicate_skipped"] = True
        append_content_record(record)
        return record

    CONTENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = CONTENT_OUTPUT_DIR / f"content-{slot.replace(':', '').replace('-', '').replace('T', '-')}.png"
    if openai_provider_enabled():
        metadata = generate_ai_content_image(image_path=image_path, timezone=timezone)
    else:
        metadata = generate_content_image(image_path=image_path, history_path=CONTENT_LOG_FILE, timezone=timezone)
    record.update(metadata)
    record["content_generated"] = image_path.exists()

    theme = metadata.get("caption_theme") or next((item for item in THEMES if item["id"] == metadata["selected_theme"]), THEMES[0])
    caption = build_caption(theme)

    image_url = ""
    try:
        image_url = upload_image(image_path, "content/latest.png")
        verify_public_url(image_url)
        record["r2_uploaded"] = True
        record["r2_url"] = image_url
    except Exception as exc:
        record["errors"]["r2"] = str(exc)

    try:
        send_telegram(image_path, caption)
        record["telegram_sent"] = True
    except Exception as exc:
        record["errors"]["telegram"] = str(exc)

    try:
        media_id = publish_instagram(image_path, caption, upload=True)
        record["instagram_published"] = True
        record["instagram_media_id"] = media_id
    except Exception as exc:
        record["errors"]["instagram"] = str(exc)

    append_content_record(record)
    return record


def publish_ai_content_post(
    *,
    timezone: str,
    send_telegram,
    publish_instagram,
    upload_image,
    verify_public_url,
) -> dict:
    slot = content_slot(timezone)
    record = {
        "scheduled_slot": slot,
        "timestamp": datetime.now(ZoneInfo(timezone)).isoformat(),
        "content_generated": False,
        "content_image_provider": "openai",
        "ai_image_generated": False,
        "r2_uploaded": False,
        "telegram_sent": False,
        "instagram_published": False,
        "errors": {},
    }
    CONTENT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = CONTENT_OUTPUT_DIR / f"content-ai-{slot.replace(':', '').replace('-', '').replace('T', '-')}.png"
    try:
        metadata = generate_ai_content_image(image_path=image_path, timezone=timezone)
        record.update(metadata)
        record["content_generated"] = image_path.exists()
        record["ai_image_generated"] = bool(metadata.get("ai_image_generated"))
    except Exception as exc:
        record["errors"]["ai_image"] = str(exc)
        append_content_record(record)
        return record

    theme = record.get("caption_theme") or next((item for item in THEMES if item["id"] == record["selected_theme"]), THEMES[0])
    caption = build_caption(theme)

    try:
        image_url = upload_image(image_path, "content/ai-latest.png")
        verify_public_url(image_url)
        record["r2_uploaded"] = True
        record["r2_url"] = image_url
    except Exception as exc:
        record["errors"]["r2"] = str(exc)

    try:
        send_telegram(image_path, caption)
        record["telegram_sent"] = True
    except Exception as exc:
        record["errors"]["telegram"] = str(exc)

    try:
        media_id = publish_instagram(image_path, caption, upload=True)
        record["instagram_published"] = True
        record["instagram_media_id"] = media_id
    except Exception as exc:
        record["errors"]["instagram"] = str(exc)

    append_content_record(record)
    return record
