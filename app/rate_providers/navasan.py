import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

DISPLAY_LABELS = {
    "usd_sell": "USD",
    "eur": "EUR",
    "aed": "AED",
    "try": "TRY",
    "sekke": "Coin",
    "gold_18k": "Gold 18K",
}


class NavasanProvider:
    def __init__(self, cache_path: Path) -> None:
        self.api_key = os.getenv("NAVASAN_API_KEY", "").strip()
        self.base_url = os.getenv("NAVASAN_BASE_URL", "https://api.navasan.tech/latest/").strip()
        self.symbols = [item.strip() for item in os.getenv(
            "NAVASAN_SYMBOLS",
            "usd_sell,eur,aed,try,sekke,gold_18k",
        ).split(",") if item.strip()]
        self.cache_path = cache_path

    def fetch(self) -> tuple[list[dict], bool]:
        if not self.api_key:
            cached = self._read_cache()
            if cached:
                log.warning("NAVASAN_API_KEY is missing; using cached Navasan rates")
                return cached, True
            raise RuntimeError("NAVASAN_API_KEY is required and no cache is available")
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    self.base_url,
                    params={"api_key": self.api_key},
                    timeout=15,
                )
                response.raise_for_status()
                payload = response.json()
                rates = self._normalize(payload)
                self._write_cache(rates)
                return rates, False
            except Exception as exc:
                last_error = exc
                log.warning("navasan fetch failed attempt=%s error=%s", attempt, exc)
                if attempt < 3:
                    time.sleep(attempt)
        cached = self._read_cache()
        if cached:
            log.warning("using cached Navasan rates after live fetch failure")
            return cached, True
        raise RuntimeError("Navasan fetch failed and no cache is available") from last_error

    def fetch_test(self) -> dict[str, str]:
        rates, cached = self.fetch()
        return {
            "source": "cache" if cached else "live",
            "symbols": ",".join(rate["symbol"] for rate in rates),
            "count": str(len(rates)),
        }

    def _normalize(self, payload: dict) -> list[dict]:
        rates: list[dict] = []
        for symbol in self.symbols:
            item = payload.get(symbol)
            if not isinstance(item, dict) or "value" not in item:
                raise ValueError(f"Navasan response missing symbol: {symbol}")
            rates.append(
                {
                    "symbol": symbol,
                    "label": DISPLAY_LABELS.get(symbol, symbol.upper()),
                    "value": str(item["value"]),
                    "unit": "IRR",
                    "note": str(item.get("date", "")).strip(),
                }
            )
        return rates

    def _write_cache(self, rates: list[dict]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rates": rates,
        }
        self.cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _read_cache(self) -> list[dict] | None:
        if not self.cache_path.exists():
            return None
        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        rates = payload.get("rates")
        return rates if isinstance(rates, list) and rates else None
