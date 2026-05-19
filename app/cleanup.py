from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from pathlib import Path

OUTPUT_DIR = Path("/app/output")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
log = logging.getLogger("omoney-rates-bot")


def cleanup_enabled() -> bool:
    return os.getenv("CLEANUP_ENABLED", "true").strip().lower() == "true"


def cleanup_keep_minutes() -> int:
    try:
        return max(1, int(os.getenv("CLEANUP_KEEP_MINUTES", "30").strip() or "30"))
    except ValueError:
        return 30


def instagram_enabled() -> bool:
    return os.getenv("INSTAGRAM_ENABLED", "").strip().lower() == "true"


def _is_safe_output_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        root = OUTPUT_DIR.resolve()
        return resolved == root or root in resolved.parents
    except OSError:
        return False


def _is_media_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS and _is_safe_output_path(path)


def _pipeline_key(path: Path) -> str:
    name = path.name.lower()
    try:
        relative = path.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return "other"
    parts = relative.parts
    if "openai-raw" in name:
        return "openai_raw"
    if len(parts) >= 2 and parts[0] == "content":
        if name.startswith("content-ai-"):
            return "content_ai"
        if name.startswith("content-"):
            return "content"
        if name in {"content-preview.png", "content-ai-preview.png"}:
            return "content_preview"
        return "content_other"
    if name.startswith("omoney-rates-"):
        return "rate"
    if name == "instagram-upload.jpg":
        return "rate_instagram_jpeg"
    if "preview" in name:
        return "preview"
    return "output_other"


def related_media_paths(image_path: Path) -> list[Path]:
    paths: list[Path] = []
    if _is_media_file(image_path):
        paths.append(image_path)
    raw_path = image_path.with_name(f"{image_path.stem}-openai-raw.png")
    if _is_media_file(raw_path):
        paths.append(raw_path)
    instagram_jpeg = OUTPUT_DIR / "instagram-upload.jpg"
    if _is_media_file(instagram_jpeg):
        paths.append(instagram_jpeg)
    return paths


def publish_cleanup_ready(record: dict, *, requires_r2: bool) -> bool:
    if not record.get("telegram_sent"):
        return False
    if instagram_enabled() and not record.get("instagram_published"):
        return False
    if requires_r2 and not record.get("r2_uploaded"):
        return False
    return True


def _delete_path(path: Path, *, dry_run: bool) -> str | None:
    if not _is_media_file(path) or not path.exists():
        return None
    if not dry_run:
        path.unlink(missing_ok=True)
        log.info("cleanup_deleted=%s", path)
    else:
        log.info("cleanup_would_delete=%s", path)
    return str(path)


def cleanup_output(*, dry_run: bool = False, force_delete: list[Path] | None = None) -> list[str]:
    if not cleanup_enabled() and not dry_run:
        return []

    deleted: list[str] = []
    seen: set[str] = set()
    cutoff = time.time() - cleanup_keep_minutes() * 60

    for path in force_delete or []:
        removed = _delete_path(path, dry_run=dry_run)
        if removed and removed not in seen:
            seen.add(removed)
            deleted.append(removed)

    files = sorted(
        (path for path in OUTPUT_DIR.rglob("*") if _is_media_file(path)),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in files:
        grouped[_pipeline_key(path)].append(path)

    protected: set[str] = set()
    for group in grouped.values():
        if group:
            protected.add(str(group[0].resolve()))

    for path in files:
        resolved = str(path.resolve())
        if resolved in seen:
            continue
        if path.stat().st_mtime >= cutoff:
            continue
        if resolved in protected:
            continue
        removed = _delete_path(path, dry_run=dry_run)
        if removed:
            seen.add(removed)
            deleted.append(removed)

    return deleted


def cleanup_after_successful_publish(record: dict, *, requires_r2: bool, dry_run: bool = False) -> list[str]:
    if not cleanup_enabled() and not dry_run:
        return []
    if not publish_cleanup_ready(record, requires_r2=requires_r2):
        return []
    force_delete: list[Path] = []
    image_path = record.get("image_path")
    if image_path:
        force_delete.extend(related_media_paths(Path(str(image_path))))
    return cleanup_output(dry_run=dry_run, force_delete=force_delete)
