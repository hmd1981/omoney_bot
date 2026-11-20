from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://fx.omoney.online"

# App-facing symbol -> Omoney FX instrument code.
#
# The app-facing symbol must stay identical to the Navasan symbol so that
# image_generator DISPLAY/ORDER tables, caption rotation and the published
# slot records keep working unchanged.
#
# TODO(verify-before-cutover): instrument codes below must be confirmed against
# GET /v1/instruments. Any mapping that does not resolve raises
# OMONEY_INSTRUMENT_UNKNOWN instead of silently dropping the row.
DEFAULT_SYMBOL_MAP: dict[str, str] = {
    "usd_sell": "USD",
    "cad": "CAD",
    "aed_sell": "AED",
    "try": "TRY",
    "omr": "OMR",
    "btc": "BTC",
    "usdt": "USDT",
    "18ayar": "GOLD18K",
}

DISPLAY_LABELS = {
    "usd_sell": "USD",
    "eur": "EUR",
    "cad": "CAD",
    "aed_sell": "AED",
    "try": "TRY",
    "omr": "OMR",
    "btc": "BTC",
    "usdt": "USDT",
    "18ayar": "Gold 18K",
    "gold_18k": "Gold 18K",
    "sekke": "Coin",
}

# Candidate payload keys. The API's exact schema is confirmed against a live
# response before cutover; these exist so a schema change fails with a precise
# diagnostic rather than a KeyError or, worse, a fabricated price.
_RECORD_LIST_KEYS = ("prices", "data", "results", "items", "instruments", "rates")
_SYMBOL_KEYS = ("instrument", "symbol", "code", "ticker", "pair", "slug", "id")
_PRICE_KEYS = ("price", "value", "last", "rate", "close")
_UNIT_KEYS = ("quote", "quote_currency", "price_unit", "unit", "currency")
_TIMESTAMP_KEYS = ("updated_at", "timestamp", "as_of", "last_updated", "price_time", "time")
_STATUS_KEYS = ("status", "state", "freshness")


class OmoneyProviderError(RuntimeError):
    """Base error for the Omoney FX provider."""


class OmoneyAuthError(OmoneyProviderError):
    """401: the API key is missing, invalid, or not permitted."""


class OmoneyRateLimitError(OmoneyProviderError):
    """429: rate limited and no snapshot could be produced."""


class OmoneyUnrecognizedPayload(OmoneyProviderError):
    """The response did not match the documented contract."""


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _first(record: dict, keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _retry_after_seconds(response: requests.Response) -> float | None:
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


class OmoneyProvider:
    """Omoney FX API adapter exposing the same interface as NavasanProvider.

    ``fetch()`` returns ``(rates, used_cache)`` where ``rates`` is a list of
    ``{symbol, label, value, unit, note}`` dicts. ``used_cache`` is True when
    the data is not a fresh live snapshot, which the caller renders as
    "Last cached update".
    """

    def __init__(self, cache_path: Path) -> None:
        self.api_key = os.getenv("OMONEY_FX_API_KEY", "").strip()
        self.base_url = os.getenv("OMONEY_FX_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
        self.symbol_map = self._load_symbol_map()
        self.cache_path = cache_path
        self.timeout = (_env_float("OMONEY_FX_CONNECT_TIMEOUT", 5.0), _env_float("OMONEY_FX_READ_TIMEOUT", 15.0))
        self.max_attempts = max(1, _env_int("OMONEY_FX_MAX_ATTEMPTS", 3))
        self.max_price_age = timedelta(minutes=_env_float("OMONEY_FX_MAX_PRICE_AGE_MINUTES", 240))
        self.max_retry_sleep = _env_float("OMONEY_FX_MAX_RETRY_SLEEP", 60.0)

    def _load_symbol_map(self) -> dict[str, str]:
        configured = os.getenv("OMONEY_SYMBOLS", "").strip()
        if not configured:
            return dict(DEFAULT_SYMBOL_MAP)
        mapping: dict[str, str] = {}
        for item in configured.split(","):
            item = item.strip()
            if not item:
                continue
            if "=" not in item:
                raise OmoneyProviderError(
                    f"OMONEY_SYMBOLS entry {item!r} must be app_symbol=INSTRUMENT"
                )
            app_symbol, instrument = item.split("=", 1)
            mapping[app_symbol.strip()] = instrument.strip()
        return mapping or dict(DEFAULT_SYMBOL_MAP)

    # ---------------------------------------------------------------- fetching

    def fetch(self) -> tuple[list[dict], bool]:
        if not self.api_key:
            cached = self._read_cache()
            if cached:
                log.warning("OMONEY_FX_API_KEY is missing; using cached Omoney FX snapshot")
                return cached, True
            raise OmoneyAuthError("OMONEY_FX_API_KEY is required and no cache is available")

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                payload = self._request_prices()
                rates, stale = self._normalize(payload)
                if stale and not rates:
                    raise OmoneyProviderError("Omoney FX returned no usable prices")
                self._write_cache(rates, stale=stale)
                return rates, stale
            except OmoneyAuthError:
                raise
            except OmoneyRateLimitError as exc:
                last_error = exc
                # Retry-After already respected inside _request_prices.
                if attempt >= self.max_attempts:
                    break
            except (OmoneyProviderError, requests.RequestException) as exc:
                last_error = exc
                log.warning("omoney fetch failed attempt=%s error=%s", attempt, exc)
                if attempt < self.max_attempts:
                    time.sleep(min(self.max_retry_sleep, float(attempt)))

        cached = self._read_cache()
        if cached:
            log.warning("using cached Omoney FX snapshot after live fetch failure")
            return cached, True
        raise OmoneyProviderError("Omoney FX fetch failed and no cache is available") from last_error

    def _request_prices(self) -> dict:
        url = f"{self.base_url}/v1/prices"
        try:
            response = requests.get(
                url,
                headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OmoneyProviderError(f"network error contacting {url}: {exc}") from exc

        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise OmoneyUnrecognizedPayload("Omoney FX returned non-JSON content") from exc

        if response.status_code == 401:
            raise OmoneyAuthError("OMONEY_FX_UNAUTHORIZED: the API key was rejected (HTTP 401)")

        if response.status_code == 429:
            wait = _retry_after_seconds(response)
            if wait is not None:
                log.warning("omoney rate limited; honoring Retry-After=%ss", wait)
                time.sleep(min(self.max_retry_sleep, wait))
            raise OmoneyRateLimitError("OMONEY_FX_RATE_LIMITED: HTTP 429")

        if 500 <= response.status_code < 600:
            raise OmoneyProviderError(f"OMONEY_FX_SERVER_ERROR: HTTP {response.status_code}")

        raise OmoneyProviderError(
            f"OMONEY_FX_UNEXPECTED_STATUS: HTTP {response.status_code}"
        )

    def fetch_test(self) -> dict[str, str]:
        rates, cached = self.fetch()
        return {
            "source": "cache" if cached else "live",
            "symbols": ",".join(rate["symbol"] for rate in rates),
            "count": str(len(rates)),
        }

    # -------------------------------------------------------------- normalizing

    def _records(self, payload: object) -> list[dict]:
        """Extract the list of price records, or raise with a schema diagnostic."""
        container: object = payload
        if isinstance(payload, dict):
            for key in _RECORD_LIST_KEYS:
                if key in payload:
                    container = payload[key]
                    break

        if isinstance(container, dict) and "error" in container:
            raise OmoneyUnrecognizedPayload(f"Omoney FX returned an error payload: {container['error']}")

        if isinstance(container, dict):
            # dict keyed by instrument: {"USD": {...}} or {"USD": 123}
            records = []
            for name, value in container.items():
                if isinstance(value, dict):
                    records.append({"_key": name, **value})
                else:
                    records.append({"_key": name, "price": value})
            return records

        if isinstance(container, list):
            records = [item for item in container if isinstance(item, dict)]
            if not records and container:
                raise OmoneyUnrecognizedPayload("Omoney FX price list contained no objects")
            return records

        observed = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
        raise OmoneyUnrecognizedPayload(f"unrecognized Omoney FX price payload; observed keys: {observed}")

    def _normalize(self, payload: object) -> tuple[list[dict], bool]:
        records = self._records(payload)
        by_instrument: dict[str, dict] = {}
        for record in records:
            name = _first(record, _SYMBOL_KEYS) or record.get("_key")
            if name is None:
                continue
            by_instrument[str(name).strip().upper()] = record
            # Allow "BTC/USD"-style pairs to also match on their base code.
            base = str(name).strip().upper().split("/")[0]
            by_instrument.setdefault(base, record)

        if not by_instrument:
            observed = sorted({key for record in records for key in record})[:20]
            raise OmoneyUnrecognizedPayload(
                f"no instrument identifiers found in Omoney FX prices; observed fields: {observed}"
            )

        rates: list[dict] = []
        missing: list[str] = []
        now = datetime.now(timezone.utc)
        stale_any = False

        for app_symbol, instrument in self.symbol_map.items():
            record = by_instrument.get(instrument.strip().upper())
            if record is None:
                missing.append(instrument)
                continue

            price = _first(record, _PRICE_KEYS)
            if price is None:
                missing.append(f"{instrument} (no price field)")
                continue

            unit = _first(record, _UNIT_KEYS)
            if unit is None:
                # Never assume IRR vs IRT. Require an explicit unit.
                raise OmoneyUnrecognizedPayload(
                    f"instrument {instrument} has no unit/quote field; refusing to guess IRR vs IRT"
                )

            status = str(_first(record, _STATUS_KEYS) or "").strip().lower()
            updated_at = _parse_iso(_first(record, _TIMESTAMP_KEYS))
            is_stale = status in {"stale", "expired", "unavailable", "error", "down"}
            if updated_at is not None and now - updated_at > self.max_price_age:
                is_stale = True
            if updated_at is None and not status:
                # No freshness metadata at all: treat as stale rather than fresh.
                is_stale = True
            stale_any = stale_any or is_stale

            note = ""
            if updated_at is not None:
                note = updated_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if is_stale:
                note = f"{note} (stale)".strip() if note else "stale"

            rates.append(
                {
                    "symbol": app_symbol,
                    "label": DISPLAY_LABELS.get(app_symbol, app_symbol.upper()),
                    "value": str(price),
                    "unit": str(unit).strip().upper(),
                    "note": note,
                    "instrument": instrument,
                    "stale": is_stale,
                }
            )

        if missing:
            available = ",".join(sorted(by_instrument))
            raise OmoneyProviderError(
                "OMONEY_INSTRUMENT_UNKNOWN: could not map "
                + ", ".join(sorted(missing))
                + f" (available: {available})"
            )

        return rates, stale_any

    # ------------------------------------------------------------------- cache

    def _write_cache(self, rates: list[dict], *, stale: bool) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "provider": "omoney",
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stale": stale,
            "rates": [{key: value for key, value in rate.items() if key != "stale"} for rate in rates],
        }
        self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _read_cache(self) -> list[dict] | None:
        if not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if payload.get("provider") not in (None, "omoney"):
            # Refuse a snapshot written by a different provider: units may differ.
            return None
        rates = payload.get("rates")
        return rates if isinstance(rates, list) and rates else None
