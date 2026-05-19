import argparse
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from PIL import Image

from app.content_posts.content_scheduler import (
    content_enabled,
    content_publish_times,
    generate_ai_content_preview,
    generate_content_preview,
    last_content_successes,
    next_content_run,
    publish_ai_content_post,
    publish_content_post,
)
from app.image_generator import generate_rate_image
from app.instagram_client import InstagramClient
from app.rate_providers.navasan import NavasanProvider
from app.storage_client import R2StorageClient
from app.telegram_client import TelegramClient

BASE_DIR = Path("/app")
CACHE_FILE = BASE_DIR / "cache" / "last_rates.json"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"
PUBLISHED_SLOTS_FILE = LOG_DIR / "published-slots.jsonl"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "omoney-rates-bot.log"),
    ],
)
log = logging.getLogger("omoney-rates-bot")

CAPTION = """اومانی، اولین صرافی با بیش از ۵۰ سال سابقه سرمایه‌گذاری و فعالیت در امارات، ترکیه و عمان، در خدمت شماست.

انواع خدمات:
• حواله ارزی
• دریافت نقدی
• واریز به حساب
• تبدیل ارز
• خدمات مالی بین‌المللی

نرخ لحظه‌ای ارز و طلا هر روز به‌صورت خودکار منتشر می‌شود.

#Omoney
#حواله_ارزی
#صرافی_عمان
#دلار
#نرخ_ارز"""


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def timezone_name() -> str:
    return os.getenv("TIMEZONE", "Asia/Muscat").strip() or "Asia/Muscat"


def publish_times() -> list[str]:
    configured = os.getenv("PUBLISH_TIMES", "").strip()
    if configured:
        return [item.strip() for item in configured.split(",") if item.strip()]
    hour = int(os.getenv("PUBLISH_HOUR", "09"))
    minute = int(os.getenv("PUBLISH_MINUTE", "00"))
    return [f"{hour:02d}:{minute:02d}"]


def current_slot(now: datetime | None = None) -> str:
    zone = ZoneInfo(timezone_name())
    when = now or datetime.now(zone)
    return when.strftime("%Y-%m-%dT%H:%M")


def preview_path() -> Path:
    return OUTPUT_DIR / "premium-reference-style-preview.png"


def generate_image(image_path: Path) -> tuple[list[dict], bool]:
    zone = ZoneInfo(timezone_name())
    now = datetime.now(zone)
    provider = NavasanProvider(CACHE_FILE)
    rates, used_cache = provider.fetch()
    generate_rate_image(
        rates=rates,
        image_path=image_path,
        title="Iran Exchange Rates",
        subtitle="Daily market snapshot",
        website=os.getenv("WEBSITE", "https://omoney.online"),
        phone=os.getenv("PHONE", "+96896129711"),
        published_at=now,
        update_note="Last cached update" if used_cache else "",
    )
    return rates, used_cache


def generate_preview() -> tuple[Path, list[dict]]:
    image_path = preview_path()
    rates, _ = generate_image(image_path)
    return image_path, rates


def send_existing_image(image_path: Path, caption: str) -> str:
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"image file does not exist: {image_path}")
    channel = required_env("TELEGRAM_CHANNEL")
    client = TelegramClient(required_env("BOT_TOKEN"))
    client.send_photo(channel=channel, image_path=image_path, caption=caption)
    return channel


def newest_png() -> Path:
    images = sorted(OUTPUT_DIR.glob("*.png"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not images:
        raise FileNotFoundError(f"no PNG images found in {OUTPUT_DIR}")
    return images[0]


def instagram_enabled() -> bool:
    return os.getenv("INSTAGRAM_ENABLED", "").strip().lower() == "true"


def verify_public_image_url(image_url: str) -> None:
    response = requests.get(image_url, timeout=30, stream=True)
    try:
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200:
            raise RuntimeError(
                "INSTAGRAM_IMAGE_PUBLIC_URL_NOT_REACHABLE: "
                f"{image_url} returned HTTP {response.status_code}"
            )
        if "image/" not in content_type.lower():
            raise RuntimeError(
                "INSTAGRAM_IMAGE_PUBLIC_URL_NOT_IMAGE: "
                f"{image_url} returned content-type {content_type or '(missing)'}"
            )
    finally:
        response.close()


def upload_image_to_r2(image_path: Path, key: str = "latest.png") -> str:
    client = R2StorageClient(
        endpoint_url=required_env("R2_ENDPOINT_URL"),
        bucket=required_env("R2_BUCKET"),
        access_key_id=required_env("R2_ACCESS_KEY_ID"),
        secret_access_key=required_env("R2_SECRET_ACCESS_KEY"),
        public_base_url=required_env("R2_PUBLIC_BASE_URL"),
    )
    return client.upload_png(image_path=image_path, key=key)


def upload_instagram_image_to_r2(image_path: Path, key: str = "instagram/latest.jpg") -> str:
    client = R2StorageClient(
        endpoint_url=required_env("R2_ENDPOINT_URL"),
        bucket=required_env("R2_BUCKET"),
        access_key_id=required_env("R2_ACCESS_KEY_ID"),
        secret_access_key=required_env("R2_SECRET_ACCESS_KEY"),
        public_base_url=required_env("R2_PUBLIC_BASE_URL"),
    )
    jpeg_path = OUTPUT_DIR / "instagram-upload.jpg"
    with Image.open(image_path) as image:
        image.convert("RGB").save(jpeg_path, "JPEG", quality=94, optimize=True, progressive=False)
    return client.upload_file(image_path=jpeg_path, key=key, content_type="image/jpeg")


def publish_instagram_image(image_path: Path, caption: str, *, upload: bool = True) -> str:
    if not instagram_enabled():
        raise RuntimeError("INSTAGRAM_ENABLED must be true")
    image_url = upload_instagram_image_to_r2(image_path) if upload else required_env("INSTAGRAM_IMAGE_PUBLIC_URL")
    verify_public_image_url(image_url)
    client = InstagramClient(
        business_account_id=required_env("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
        access_token=required_env("INSTAGRAM_ACCESS_TOKEN"),
        base_url=os.getenv("INSTAGRAM_API_BASE_URL", "https://graph.facebook.com").strip(),
    )
    return client.publish_image(image_url=image_url, caption=caption)


def publish_instagram_preview() -> tuple[Path, list[dict], str]:
    image_path, rates = generate_preview()
    media_id = publish_instagram_image(image_path=image_path, caption=CAPTION)
    return image_path, rates, media_id


def load_slot_records() -> list[dict]:
    if not PUBLISHED_SLOTS_FILE.exists():
        return []
    records: list[dict] = []
    for line in PUBLISHED_SLOTS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("ignored invalid published slot record")
    return records


def append_slot_record(record: dict) -> None:
    PUBLISHED_SLOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PUBLISHED_SLOTS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def slot_already_completed(slot: str) -> bool:
    for record in load_slot_records():
        if record.get("scheduled_slot") == slot and record.get("telegram_sent") and record.get("instagram_published"):
            return True
    return False


def slot_channel_successes(slot: str) -> dict[str, bool]:
    successes = {"telegram": False, "instagram": False}
    for record in load_slot_records():
        if record.get("scheduled_slot") != slot:
            continue
        if record.get("telegram_sent"):
            successes["telegram"] = True
        if record.get("instagram_published"):
            successes["instagram"] = True
    return successes


def publish_scheduled_slot(slot: str | None = None) -> dict:
    slot_id = slot or current_slot()
    prior_successes = slot_channel_successes(slot_id)
    record = {
        "scheduled_slot": slot_id,
        "timestamp": datetime.now(ZoneInfo(timezone_name())).isoformat(),
        "rates_fetched": False,
        "cached": False,
        "image_generated": False,
        "r2_uploaded": False,
        "telegram_sent": False,
        "instagram_published": False,
        "errors": {},
    }
    if slot_already_completed(slot_id):
        record["duplicate_skipped"] = True
        append_slot_record(record)
        log.info("scheduled_publish %s", json.dumps(record, ensure_ascii=False, sort_keys=True))
        return record

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = OUTPUT_DIR / f"omoney-rates-{slot_id.replace(':', '').replace('-', '').replace('T', '-')}.png"

    try:
        rates, used_cache = generate_image(image_path)
        record["rates_fetched"] = True
        record["cached"] = used_cache
        record["image_generated"] = image_path.exists()
        record["symbols"] = [str(rate.get("symbol", "")) for rate in rates]
    except Exception as exc:
        record["errors"]["generation"] = str(exc)
        append_slot_record(record)
        log.error("scheduled_publish %s", json.dumps(record, ensure_ascii=False, sort_keys=True))
        return record

    image_url = ""
    if instagram_enabled() and not prior_successes["instagram"]:
        try:
            image_url = upload_image_to_r2(image_path)
            verify_public_image_url(image_url)
            record["r2_uploaded"] = True
            record["image_url"] = image_url
        except Exception as exc:
            record["errors"]["r2"] = str(exc)
    else:
        record["r2_uploaded"] = False

    if prior_successes["telegram"]:
        record["telegram_sent"] = True
        record["telegram_duplicate_skipped"] = True
    else:
        try:
            send_existing_image(image_path, CAPTION)
            record["telegram_sent"] = True
        except Exception as exc:
            record["errors"]["telegram"] = str(exc)

    if instagram_enabled() and prior_successes["instagram"]:
        record["instagram_published"] = True
        record["instagram_duplicate_skipped"] = True
    elif instagram_enabled():
        try:
            media_id = publish_instagram_image(image_path=image_path, caption=CAPTION, upload=True)
            record["instagram_published"] = True
            record["instagram_media_id"] = media_id
        except Exception as exc:
            record["errors"]["instagram"] = str(exc)

    append_slot_record(record)
    level = logging.INFO if record["telegram_sent"] and (record["instagram_published"] or not instagram_enabled()) else logging.ERROR
    log.log(level, "scheduled_publish %s", json.dumps(record, ensure_ascii=False, sort_keys=True))
    return record


def publish_once() -> Path:
    record = publish_scheduled_slot(current_slot())
    slot = str(record.get("scheduled_slot", current_slot()))
    return OUTPUT_DIR / f"omoney-rates-{slot.replace(':', '').replace('-', '').replace('T', '-')}.png"


def next_scheduled_run(now: datetime | None = None) -> str:
    zone = ZoneInfo(timezone_name())
    current = now or datetime.now(zone)
    candidates: list[datetime] = []
    for item in publish_times():
        hour_text, minute_text = item.split(":", 1)
        candidate = current.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
        if candidate <= current:
            candidate = candidate + timedelta(days=1)
        candidates.append(candidate)
    return min(candidates).isoformat() if candidates else ""


def last_success_by_channel() -> dict:
    result = {"telegram": "", "instagram": ""}
    for record in load_slot_records():
        slot = str(record.get("scheduled_slot", ""))
        if record.get("telegram_sent"):
            result["telegram"] = slot
        if record.get("instagram_published"):
            result["instagram"] = slot
    return result


def print_schedule_status() -> None:
    successes = last_success_by_channel()
    print(f"timezone={timezone_name()}")
    print("publish_times=" + ",".join(publish_times()))
    print(f"next_scheduled_run={next_scheduled_run()}")
    print("telegram_enabled=" + str(bool(os.getenv("TELEGRAM_CHANNEL", "").strip())).lower())
    print("instagram_enabled=" + str(instagram_enabled()).lower())
    print(f"last_success_telegram={successes['telegram'] or 'none'}")
    print(f"last_success_instagram={successes['instagram'] or 'none'}")


def print_content_schedule_status() -> None:
    successes = last_content_successes()
    print(f"timezone={timezone_name()}")
    print("content_enabled=" + str(content_enabled()).lower())
    print("content_publish_times=" + ",".join(content_publish_times()))
    print(f"next_content_run={next_content_run(timezone_name())}")
    print("telegram_enabled=" + str(bool(os.getenv("TELEGRAM_CHANNEL", "").strip())).lower())
    print("instagram_enabled=" + str(instagram_enabled()).lower())
    print(f"last_content_success_telegram={successes['telegram'] or 'none'}")
    print(f"last_content_success_instagram={successes['instagram'] or 'none'}")


def send_content_telegram(image_path: Path, caption: str) -> str:
    return send_existing_image(image_path, caption)


def publish_content_now(scheduled_time: str | None = None) -> dict:
    return publish_content_post(
        timezone=timezone_name(),
        scheduled_time=scheduled_time,
        send_telegram=send_content_telegram,
        publish_instagram=publish_instagram_image,
        upload_image=upload_image_to_r2,
        verify_public_url=verify_public_image_url,
    )


def publish_ai_content_now() -> dict:
    return publish_ai_content_post(
        timezone=timezone_name(),
        send_telegram=send_content_telegram,
        publish_instagram=publish_instagram_image,
        upload_image=upload_image_to_r2,
        verify_public_url=verify_public_image_url,
    )


def run_scheduler() -> None:
    timezone_value = timezone_name()
    schedules = publish_times()
    scheduler = BlockingScheduler(timezone=timezone_value)
    for item in schedules:
        hour_text, minute_text = item.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        scheduler.add_job(
            lambda scheduled_time=item: publish_scheduled_slot(
                datetime.now(ZoneInfo(timezone_value)).strftime("%Y-%m-%d") + "T" + scheduled_time
            ),
            CronTrigger(hour=hour, minute=minute, timezone=timezone_value),
            id=f"daily-rate-publish-{hour:02d}{minute:02d}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    if content_enabled():
        for item in content_publish_times():
            hour_text, minute_text = item.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
            scheduler.add_job(
                lambda scheduled_time=item: publish_content_now(scheduled_time),
                CronTrigger(hour=hour, minute=minute, timezone=timezone_value),
                id=f"content-publish-{hour:02d}{minute:02d}",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
        log.info("content scheduler enabled timezone=%s times=%s", timezone_value, ",".join(content_publish_times()))
    log.info("scheduler started timezone=%s times=%s", timezone_value, ",".join(schedules))
    scheduler.start()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-now", action="store_true", help="Generate and publish one image immediately")
    parser.add_argument("--fetch-test", action="store_true", help="Fetch and normalize live/cache Navasan rates")
    parser.add_argument("--preview-only", action="store_true", help="Generate preview image without Telegram publishing")
    parser.add_argument("--preview-send", action="store_true", help="Generate preview image and send it to Telegram")
    parser.add_argument("--send-latest", action="store_true", help="Send newest PNG from output without regenerating")
    parser.add_argument("--instagram-test", action="store_true", help="Generate preview image and publish one Instagram feed test post")
    parser.add_argument("--print-caption", action="store_true", help="Print the unified publishing caption")
    parser.add_argument("--schedule-status", action="store_true", help="Print scheduler status")
    parser.add_argument("--content-preview", action="store_true", help="Generate one premium content image without publishing")
    parser.add_argument("--content-send", action="store_true", help="Generate and publish one premium content image")
    parser.add_argument("--content-ai-preview", action="store_true", help="Generate one OpenAI-backed premium content image without publishing")
    parser.add_argument("--content-ai-send", action="store_true", help="Generate and publish one OpenAI-backed premium content image")
    parser.add_argument("--content-schedule-status", action="store_true", help="Print content scheduler status")
    args = parser.parse_args()
    if args.fetch_test:
        result = NavasanProvider(CACHE_FILE).fetch_test()
        log.info("fetch test source=%s count=%s symbols=%s", result["source"], result["count"], result["symbols"])
        print(f"source={result['source']} count={result['count']} symbols={result['symbols']}")
        return
    if args.print_caption:
        print(CAPTION)
        return
    if args.schedule_status:
        print_schedule_status()
        return
    if args.content_schedule_status:
        print_content_schedule_status()
        return
    if args.content_preview:
        image_path, metadata, caption = generate_content_preview(timezone_name())
        from PIL import Image
        with Image.open(image_path) as image:
            print(f"output={image_path}")
            print(f"resolution={image.size[0]}x{image.size[1]}")
        print(f"selected_theme={metadata['selected_theme']}")
        print(f"selected_visual_preset={metadata['selected_visual_preset']}")
        print("caption_preview=" + caption.splitlines()[0])
        return
    if args.content_ai_preview:
        try:
            image_path, metadata, caption = generate_ai_content_preview(timezone_name())
        except RuntimeError as exc:
            raise SystemExit(f"error: {exc}") from None
        from PIL import Image
        with Image.open(image_path) as image:
            print(f"output={image_path}")
            print(f"resolution={image.size[0]}x{image.size[1]}")
        print(f"content_image_provider={metadata.get('content_image_provider', '')}")
        print(f"selected_theme={metadata.get('selected_theme', '')}")
        print(f"selected_ai_prompt_theme={metadata.get('selected_ai_prompt_theme', '')}")
        print(f"ai_image_generated={str(metadata.get('ai_image_generated', False)).lower()}")
        print("caption_preview=" + caption.splitlines()[0])
        return
    if args.content_send:
        record = publish_content_now()
        print("content_generated=" + str(record.get("content_generated", False)).lower())
        print("telegram_sent=" + str(record.get("telegram_sent", False)).lower())
        print("instagram_published=" + str(record.get("instagram_published", False)).lower())
        print(f"selected_theme={record.get('selected_theme', '')}")
        print(f"selected_visual_preset={record.get('selected_visual_preset', '')}")
        print(f"image_path={record.get('image_path', '')}")
        print(f"r2_url={record.get('r2_url', '')}")
        if record.get("errors"):
            print("errors=" + json.dumps(record["errors"], ensure_ascii=False, sort_keys=True))
        return
    if args.content_ai_send:
        record = publish_ai_content_now()
        print("content_image_provider=" + str(record.get("content_image_provider", "")))
        print("ai_image_generated=" + str(record.get("ai_image_generated", False)).lower())
        print("telegram_sent=" + str(record.get("telegram_sent", False)).lower())
        print("instagram_published=" + str(record.get("instagram_published", False)).lower())
        print(f"selected_theme={record.get('selected_theme', '')}")
        print(f"selected_ai_prompt_theme={record.get('selected_ai_prompt_theme', '')}")
        print(f"image_path={record.get('image_path', '')}")
        print(f"r2_url={record.get('r2_url', '')}")
        if record.get("errors"):
            print("errors=" + json.dumps(record["errors"], ensure_ascii=False, sort_keys=True))
        return
    if args.send_now:
        publish_once()
        return
    if args.preview_only:
        image_path, rates = generate_preview()
        from PIL import Image
        with Image.open(image_path) as image:
            print(f"output={image_path}")
            print(f"resolution={image.size[0]}x{image.size[1]}")
        print("symbols=" + ",".join(str(rate.get("symbol", "")) for rate in rates))
        return
    if args.preview_send:
        image_path, rates = generate_preview()
        channel = send_existing_image(image_path, CAPTION)
        print("preview_generated=true")
        print("telegram_sent=true")
        print(f"channel={channel}")
        print(f"image_path={image_path}")
        print("symbols=" + ",".join(str(rate.get("symbol", "")) for rate in rates))
        return
    if args.send_latest:
        image_path = newest_png()
        print(f"selected_image={image_path}")
        channel = send_existing_image(image_path, CAPTION)
        print("telegram_sent=true")
        print(f"channel={channel}")
        print(f"image_path={image_path}")
        return
    if args.instagram_test:
        try:
            image_path, rates, media_id = publish_instagram_preview()
        except RuntimeError as exc:
            raise SystemExit(f"error: {exc}") from None
        print("preview_generated=true")
        print("instagram_published=true")
        print(f"media_id={media_id}")
        print(f"image_path={image_path}")
        print("symbols=" + ",".join(str(rate.get("symbol", "")) for rate in rates))
        return
    run_scheduler()


if __name__ == "__main__":
    main()
