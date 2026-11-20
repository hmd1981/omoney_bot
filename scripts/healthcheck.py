"""Read-only health check for the Omoney rates bot.

Runs inside the container. Never publishes, never mutates configuration,
never restarts anything. Prints the API key fingerprint only, never the key.

Exit code: 0 when every check passes, otherwise the number of failures.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

FAILED = 0
PASS_MARK = "\033[32mPASS\033[0m"
FAIL_MARK = "\033[31mFAIL\033[0m"
INFO_MARK = "----"


def pass_(text: str) -> None:
    print(f"  {PASS_MARK}  {text}")


def fail(text: str) -> None:
    global FAILED
    FAILED += 1
    print(f"  {FAIL_MARK}  {text}")


def info(text: str) -> None:
    print(f"  {INFO_MARK}  {text}")


def section(n: int, total: int, title: str) -> None:
    print(f"[{n}/{total}] {title}")


def key_value() -> str:
    return os.getenv("OMONEY_FX_API_KEY", "").strip()


def provider_name() -> str:
    return os.getenv("CURRENCY_PROVIDER", "navasan").strip().lower() or "navasan"


def cache_path() -> Path:
    base = Path("/app/cache")
    return base / ("last_rates_omoney.json" if provider_name() == "omoney" else "last_rates.json")


def cache_age_minutes() -> float | None:
    try:
        payload = json.loads(cache_path().read_text(encoding="utf-8"))
        raw = payload.get("fetched_at") or payload.get("timestamp") or ""
        when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - when).total_seconds() / 60
    except Exception:
        return None


TOTAL = 7


def check_provider() -> None:
    section(1, TOTAL, "Container")
    # If this runs, the container is alive.
    pass_("container is running")


def check_key() -> None:
    section(2, TOTAL, "Provider and key")
    name = provider_name()
    key = key_value()
    fingerprint = hashlib.sha256(key.encode()).hexdigest()[:16] if key else "none"
    tail = key[-4:] if key else "none"
    info(f"provider={name}  key_fingerprint={fingerprint}  key_tail=****{tail}")
    if name == "omoney":
        pass_("provider is omoney")
    else:
        fail(f"provider is {name!r}, expected 'omoney'")
    if key:
        pass_("OMONEY_FX_API_KEY is present")
    else:
        fail("OMONEY_FX_API_KEY is empty")


def check_live_api() -> None:
    section(3, TOTAL, "Live API (authenticated)")
    base = os.getenv("OMONEY_FX_BASE_URL", "https://fx.omoney.online").strip().rstrip("/")
    try:
        response = requests.get(
            f"{base}/v1/prices", headers={"X-Api-Key": key_value()}, timeout=(5, 15)
        )
    except Exception as exc:  # noqa: BLE001
        fail(f"request failed: {type(exc).__name__}")
        return

    info(f"GET /v1/prices -> HTTP {response.status_code}")
    if response.status_code != 200:
        fail(f"HTTP {response.status_code} (key rejected or API down)")
        return
    pass_("authenticated request succeeded")

    try:
        payload = response.json()
    except ValueError:
        fail("response was not valid JSON")
        return

    prices = payload.get("prices") or []
    quote = payload.get("quote_currency")
    statuses: dict[str, int] = {}
    for item in prices:
        statuses[str(item.get("status"))] = statuses.get(str(item.get("status")), 0) + 1
    info(f"count={len(prices)} quote={quote} statuses={statuses}")

    if not prices:
        fail("no prices returned")
        return
    priced = [p for p in prices if isinstance(p.get("price"), (int, float)) and p["price"] > 0]
    if priced:
        pass_(f"{len(priced)}/{len(prices)} instruments carry a positive price")
    else:
        fail("no instrument carries a usable price")
    if quote == "IRT":
        pass_("quote currency is IRT (toman)")
    elif quote:
        info(f"quote currency is {quote}")


def check_app_fetch() -> None:
    section(4, TOTAL, "Provider fetch (app code path)")
    try:
        from app.main import build_rate_provider, rate_provider_name
    except Exception as exc:  # noqa: BLE001
        fail(f"could not import app: {exc}")
        return
    try:
        rates, used_cache = build_rate_provider().fetch()
    except Exception as exc:  # noqa: BLE001
        fail(f"fetch raised {type(exc).__name__}: {exc}")
        return
    symbols = ",".join(str(r.get("symbol", "")) for r in rates)
    info(f"provider={rate_provider_name()} rows={len(rates)} cached={used_cache}")
    info(f"symbols={symbols}")
    if used_cache:
        age = cache_age_minutes()
        age_text = f"{age:.0f} min" if age is not None else "unknown"
        fail(f"serving CACHE, not live data (cache age {age_text})")
    else:
        pass_("live data from provider")


def check_r2() -> None:
    section(5, TOTAL, "R2 storage")
    try:
        import boto3
    except Exception as exc:  # noqa: BLE001
        fail(f"boto3 unavailable: {exc}")
        return
    endpoint = os.getenv("R2_ENDPOINT") or (
        f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com"
    )
    try:
        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        head = client.head_object(Bucket=os.getenv("R2_BUCKET"), Key="latest.png")
        info(f"latest.png size={head['ContentLength']} bytes")
        pass_("R2 reachable and latest.png present")
    except Exception as exc:  # noqa: BLE001
        fail(f"R2 check failed: {type(exc).__name__}")


def check_instagram() -> None:
    section(6, TOTAL, "Instagram token")
    try:
        from app.instagram_token import inspect_access_token
    except Exception:
        inspect_access_token = None
    if inspect_access_token is None:
        info("token helper unavailable; falling back to env presence")
        token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
        (pass_ if token else fail)("INSTAGRAM_ACCESS_TOKEN " + ("present" if token else "missing"))
        return
    try:
        status = inspect_access_token(
            os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
            os.getenv("INSTAGRAM_APP_ID", ""),
            os.getenv("INSTAGRAM_APP_SECRET", ""),
        )
    except Exception as exc:  # noqa: BLE001
        fail(f"token check raised {type(exc).__name__}")
        return
    info(
        f"valid={status.valid} expires_at={status.expires_text()} "
        f"days_remaining={status.days_remaining_text()} error={status.error or 'none'}"
    )
    if status.valid:
        pass_("Instagram token is valid")
    else:
        fail(f"Instagram token is invalid ({status.error or 'no detail'})")


def check_schedule() -> None:
    section(7, TOTAL, "Schedule")
    try:
        from app.main import next_scheduled_run, publish_times, timezone_name
    except Exception as exc:  # noqa: BLE001
        fail(f"could not import scheduler config: {exc}")
        return
    times = publish_times()
    nxt = next_scheduled_run()
    info(f"timezone={timezone_name()}")
    info(f"publish_times={','.join(times)}")
    info(f"next_scheduled_run={nxt}")
    info(f"telegram_enabled={bool(os.getenv('TELEGRAM_CHANNEL', '').strip())}")
    info(f"instagram_enabled={os.getenv('INSTAGRAM_ENABLED', '').strip().lower() == 'true'}")
    if times and nxt:
        pass_("publish schedule is configured")
    else:
        fail("publish schedule is missing")


def main() -> int:
    print("=" * 46)
    print(" Omoney rates bot health check")
    print(" " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"))
    print("=" * 46)
    print()
    for step in (
        check_provider,
        check_key,
        check_live_api,
        check_app_fetch,
        check_r2,
        check_instagram,
        check_schedule,
    ):
        try:
            step()
        except Exception as exc:  # noqa: BLE001
            fail(f"{step.__name__} crashed: {type(exc).__name__}: {exc}")
        print()
    print("=" * 46)
    if FAILED == 0:
        print(" RESULT: ALL CHECKS PASSED")
    else:
        print(f" RESULT: {FAILED} CHECK(S) FAILED")
    print("=" * 46)
    return FAILED


if __name__ == "__main__":
    raise SystemExit(main())
