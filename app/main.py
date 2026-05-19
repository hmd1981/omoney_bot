import argparse
import logging
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.image_generator import generate_rate_image
from app.instagram_client import InstagramClient
from app.rate_providers.navasan import NavasanProvider
from app.storage_client import R2StorageClient
from app.telegram_client import TelegramClient

BASE_DIR = Path("/app")
CACHE_FILE = BASE_DIR / "cache" / "last_rates.json"
OUTPUT_DIR = BASE_DIR / "output"
LOG_DIR = BASE_DIR / "logs"

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


def preview_path() -> Path:
    return OUTPUT_DIR / "premium-reference-style-preview.png"


def generate_preview() -> tuple[Path, list[dict]]:
    timezone = ZoneInfo(os.getenv("TIMEZONE", "Asia/Muscat"))
    now = datetime.now(timezone)
    provider = NavasanProvider(CACHE_FILE)
    rates, used_cache = provider.fetch()
    image_path = preview_path()
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


def publish_instagram_image(image_path: Path, caption: str) -> str:
    if not instagram_enabled():
        raise RuntimeError("INSTAGRAM_ENABLED must be true")
    image_url = upload_image_to_r2(image_path)
    verify_public_image_url(image_url)
    configured_url = os.getenv("INSTAGRAM_IMAGE_PUBLIC_URL", "").strip()
    if configured_url and configured_url != image_url:
        raise RuntimeError(
            "INSTAGRAM_IMAGE_PUBLIC_URL_MISMATCH: "
            f"configured={configured_url} uploaded={image_url}"
        )
    client = InstagramClient(
        business_account_id=required_env("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
        access_token=required_env("INSTAGRAM_ACCESS_TOKEN"),
        base_url=os.getenv("INSTAGRAM_API_BASE_URL", "https://graph.facebook.com").strip(),
    )
    media_id = client.publish_image(
        image_url=image_url,
        caption=caption,
    )
    return media_id


def publish_instagram_preview() -> tuple[Path, list[dict], str]:
    image_path, rates = generate_preview()
    media_id = publish_instagram_image(image_path=image_path, caption=CAPTION)
    return image_path, rates, media_id


def publish_once() -> Path:
    timezone = ZoneInfo(os.getenv("TIMEZONE", "Asia/Muscat"))
    now = datetime.now(timezone)
    provider = NavasanProvider(CACHE_FILE)
    rates, used_cache = provider.fetch()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    image_path = OUTPUT_DIR / f"omoney-rates-{now:%Y%m%d-%H%M%S}.png"
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
    client = TelegramClient(required_env("BOT_TOKEN"))
    channel = required_env("TELEGRAM_CHANNEL")
    client.send_photo(channel=channel, image_path=image_path, caption=CAPTION)
    log.info("published telegram image=%s channel=%s", image_path.name, channel)
    if instagram_enabled():
        media_id = publish_instagram_image(image_path=image_path, caption=CAPTION)
        log.info("published instagram image=%s media_id=%s", image_path.name, media_id)
    return image_path


def run_scheduler() -> None:
    timezone_name = os.getenv("TIMEZONE", "Asia/Muscat")
    publish_times = os.getenv("PUBLISH_TIMES", "").strip()
    if publish_times:
        schedules = [item.strip() for item in publish_times.split(",") if item.strip()]
    else:
        schedules = [f"{int(os.getenv('PUBLISH_HOUR', '09')):02d}:{int(os.getenv('PUBLISH_MINUTE', '00')):02d}"]
    scheduler = BlockingScheduler(timezone=timezone_name)
    for item in schedules:
        hour_text, minute_text = item.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
        scheduler.add_job(
            publish_once,
            CronTrigger(hour=hour, minute=minute, timezone=timezone_name),
            id=f"daily-rate-publish-{hour:02d}{minute:02d}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    log.info("scheduler started timezone=%s times=%s", timezone_name, ",".join(schedules))
    scheduler.start()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send-now", action="store_true", help="Generate and publish one image immediately")
    parser.add_argument("--fetch-test", action="store_true", help="Fetch and normalize live/cache Navasan rates")
    parser.add_argument("--preview-only", action="store_true", help="Generate preview image without Telegram publishing")
    parser.add_argument("--preview-send", action="store_true", help="Generate preview image and send it to Telegram")
    parser.add_argument("--send-latest", action="store_true", help="Send newest PNG from output without regenerating")
    parser.add_argument("--instagram-test", action="store_true", help="Generate preview image and publish one Instagram feed test post")
    args = parser.parse_args()
    if args.fetch_test:
        result = NavasanProvider(CACHE_FILE).fetch_test()
        log.info("fetch test source=%s count=%s symbols=%s", result["source"], result["count"], result["symbols"])
        print(f"source={result['source']} count={result['count']} symbols={result['symbols']}")
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
