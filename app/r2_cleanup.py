from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.storage_client import R2StorageClient

log = logging.getLogger("omoney-rates-bot")

ALLOWED_PREFIXES = (
    "archive/",
    "content/archive/",
    "content/previews/",
    "instagram/archive/",
)
PROTECTED_KEYS = frozenset(
    {
        "latest.png",
        "content/latest.png",
        "instagram/latest.jpg",
    }
)
ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
PUBLISHING_LATEST_KEYS = frozenset(
    {
        "latest.png",
        "content/latest.png",
        "content/ai-latest.png",
        "instagram/latest.jpg",
    }
)


@dataclass
class R2CleanupResult:
    dry_run: bool
    objects: list[dict] = field(default_factory=list)
    deleted_keys: list[str] = field(default_factory=list)
    total_bytes: int = 0
    error: str = ""


def r2_cleanup_enabled() -> bool:
    return os.getenv("R2_CLEANUP_ENABLED", "true").strip().lower() == "true"


def r2_cleanup_keep_hours() -> int:
    try:
        return max(1, int(os.getenv("R2_CLEANUP_KEEP_HOURS", "48").strip() or "48"))
    except ValueError:
        return 48


def _missing_r2_env() -> list[str]:
    missing: list[str] = []
    for name in ("R2_ENDPOINT_URL", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        if not os.getenv(name, "").strip():
            missing.append(name)
    return missing


def _normalize_key(key: str) -> str:
    return key.lstrip("/")


def _build_client() -> tuple[R2StorageClient | None, str]:
    missing = _missing_r2_env()
    if missing:
        return None, "missing R2 env: " + ", ".join(missing)
    client = R2StorageClient(
        endpoint_url=os.getenv("R2_ENDPOINT_URL", "").strip(),
        bucket=os.getenv("R2_BUCKET", "").strip(),
        access_key_id=os.getenv("R2_ACCESS_KEY_ID", "").strip(),
        secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", "").strip(),
        public_base_url=os.getenv("R2_PUBLIC_BASE_URL", "https://example.invalid").strip(),
    )
    return client, ""


def _allowed_media_key(key: str) -> bool:
    normalized = _normalize_key(key)
    if normalized in PROTECTED_KEYS or normalized in PUBLISHING_LATEST_KEYS:
        return False
    if not any(normalized.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return False
    lowered = normalized.lower()
    if not lowered.endswith(ALLOWED_EXTENSIONS):
        return False
    return True


def _list_candidates(client: R2StorageClient) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=r2_cleanup_keep_hours())
    paginator = client._client.get_paginator("list_objects_v2")
    candidates: list[dict] = []
    for prefix in ALLOWED_PREFIXES:
        for page in paginator.paginate(Bucket=client._bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                key = _normalize_key(str(item.get("Key", "")))
                if not key or not _allowed_media_key(key):
                    continue
                last_modified = item.get("LastModified")
                if not isinstance(last_modified, datetime):
                    continue
                if last_modified.tzinfo is None:
                    last_modified = last_modified.replace(tzinfo=timezone.utc)
                if last_modified >= cutoff:
                    continue
                size = int(item.get("Size") or 0)
                candidates.append(
                    {
                        "key": key,
                        "size": size,
                        "last_modified": last_modified.isoformat(),
                    }
                )
    candidates.sort(key=lambda item: item["key"])
    return candidates


def run_r2_cleanup(*, dry_run: bool) -> R2CleanupResult:
    result = R2CleanupResult(dry_run=dry_run)
    if not r2_cleanup_enabled() and not dry_run:
        result.error = "R2 cleanup disabled (R2_CLEANUP_ENABLED=false)"
        return result

    client, error = _build_client()
    if client is None:
        result.error = error
        return result

    try:
        result.objects = _list_candidates(client)
        result.total_bytes = sum(int(item.get("size") or 0) for item in result.objects)
    except Exception as exc:
        result.error = f"R2 list failed: {exc}"
        log.error("r2_cleanup_error=%s", result.error)
        return result

    if dry_run or not r2_cleanup_enabled():
        return result

    for item in result.objects:
        key = str(item["key"])
        try:
            client._client.delete_object(Bucket=client._bucket, Key=key)
            result.deleted_keys.append(key)
            log.info("r2_cleanup_deleted=%s", key)
        except Exception as exc:
            log.error("r2_cleanup_delete_failed key=%s error=%s", key, exc)

    return result
