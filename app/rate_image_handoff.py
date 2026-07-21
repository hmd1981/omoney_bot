from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from PIL import Image

log = logging.getLogger("omoney-rates-bot")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log_rate_image_handoff(phase: str, path: Path, image_hash: str) -> None:
    resolved = path.resolve()
    if phase == "telegram":
        log.info("telegram_upload_source=%s", resolved)
        log.info("telegram_image_hash=%s", image_hash)
        print(f"telegram_upload_source={resolved}")
        print(f"telegram_image_hash={image_hash}")
        return
    log.info("instagram_upload_source=%s", resolved)
    log.info("instagram_image_hash=%s", image_hash)
    print(f"instagram_upload_source={resolved}")
    print(f"instagram_image_hash={image_hash}")


def assert_canonical_hash_unchanged(canonical: Path, expected_hash: str) -> None:
    current = sha256_file(canonical)
    if current != expected_hash:
        raise RuntimeError(
            "canonical rate image hash changed: "
            f"expected={expected_hash} current={current} path={canonical.resolve()}"
        )


def assert_telegram_instagram_hash_match(telegram_hash: str, instagram_hash: str) -> None:
    if telegram_hash != instagram_hash:
        raise RuntimeError(
            "telegram_image_hash != instagram_image_hash: "
            f"telegram={telegram_hash} instagram={instagram_hash}"
        )


def instagram_jpeg_path_for(canonical_png: Path) -> Path:
    return canonical_png.with_name(f"{canonical_png.stem}-instagram.jpg")


def build_instagram_jpeg_from_canonical(canonical_png: Path) -> Path:
    canonical = canonical_png.resolve()
    if not canonical.exists():
        raise FileNotFoundError(f"canonical rate image does not exist: {canonical}")
    jpeg_path = instagram_jpeg_path_for(canonical)
    with Image.open(canonical) as image:
        image.convert("RGB").save(jpeg_path, "JPEG", quality=94, optimize=True, progressive=False)
    return jpeg_path.resolve()
