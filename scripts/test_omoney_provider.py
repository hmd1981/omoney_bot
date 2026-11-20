"""Deterministic failure-mode tests for OmoneyProvider.

Runs a local mock server so 429/Retry-After, 5xx, 401, timeout and malformed
payloads can be exercised without touching the real API or relying on luck.
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.rate_providers import omoney  # noqa: E402  (PYTHONPATH=/app)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def make_handler(state: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state["hits"] = state.get("hits", 0) + 1
            mode = state.get("mode")

            if mode == "empty_then_ok":
                if state["hits"] == 1:
                    return self._send(429, {"error": "rate limited"}, {"Retry-After": "1"})
                return self._send(200, OK_PAYLOAD)

            if mode == "always_429":
                return self._send(429, {"error": "rate limited"}, {"Retry-After": "0"})
            if mode == "401":
                return self._send(401, {"error": {"code": "unauthorized", "message": "invalid API key"}})
            if mode == "500":
                return self._send(500, {"error": "boom"})
            if mode == "slow":
                time.sleep(3)
                return self._send(200, OK_PAYLOAD)
            if mode == "not_json":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html>oops</html>")
                return
            if mode == "no_unit":
                payload = json.loads(json.dumps(OK_PAYLOAD))
                for p in payload["prices"]:
                    p.pop("quote_currency", None)
                payload.pop("quote_currency", None)
                return self._send(200, payload)
            if mode == "unavailable":
                payload = json.loads(json.dumps(OK_PAYLOAD))
                for p in payload["prices"]:
                    p["status"] = "unavailable"
                    p["price"] = None
                    p["sell_price"] = None
                return self._send(200, payload)
            if mode == "stale":
                payload = json.loads(json.dumps(OK_PAYLOAD))
                for p in payload["prices"]:
                    p["status"] = "stale"
                return self._send(200, payload)
            if mode == "zero_sell":
                payload = json.loads(json.dumps(OK_PAYLOAD))
                for p in payload["prices"]:
                    p["sell_price"] = 0
                return self._send(200, payload)
            if mode == "bad_price":
                payload = json.loads(json.dumps(OK_PAYLOAD))
                for p in payload["prices"]:
                    p["price"] = "not-a-number"
                    p["sell_price"] = None
                return self._send(200, payload)
            return self._send(200, OK_PAYLOAD)

        def _send(self, code, body, headers=None):
            raw = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def rec(symbol, price, sell=None, status="fresh", quote="IRT", age=30):
    return {
        "symbol": symbol, "instrument_type": "fiat", "quote_currency": quote,
        "price": price, "sell_price": sell, "buy_price": price,
        "unit": "Toman per 1 unit", "lot_size": 1,
        "source_updated_at": "2026-11-20T13:30:11Z", "age_seconds": age,
        "status": status, "derived": False, "warnings": [],
    }


OK_PAYLOAD = {
    "snapshot_id": "mock", "quote_currency": "IRT", "rate_side": "mid", "mode": "live",
    "count": 7,
    "prices": [
        rec("USD", 272575.0, 271200.0), rec("CAD", 190050.0), rec("AED", 74215.0, 73840.0),
        rec("TRY", 5425.0), rec("OMR", 704400.0), rec("BTC", 16894126572.0),
        rec("USDT", 274758.0, 0),
    ],
}


def run(mode: str, **env):
    state = {"mode": mode}
    server = HTTPServer(("127.0.0.1", 0), make_handler(state))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    saved = dict(os.environ)
    os.environ["OMONEY_FX_API_KEY"] = "test-key-not-real"
    os.environ["OMONEY_FX_BASE_URL"] = f"http://127.0.0.1:{port}"
    os.environ["OMONEY_FX_MAX_RETRY_SLEEP"] = "2"
    os.environ["OMONEY_FX_READ_TIMEOUT"] = "1"
    os.environ.update({k: str(v) for k, v in env.items()})
    server_ref = server
    return _call(state, server_ref, saved)


def _call(state, server, saved):

    cache = Path("/tmp/mock-cache.json")
    cache.unlink(missing_ok=True)
    provider = omoney.OmoneyProvider(cache)
    state["fetch_started"] = time.time()
    try:
        started = time.time()
        out = provider.fetch()
        state["fetch_elapsed"] = time.time() - started
        return out, state, provider, omoney
    except Exception as exc:  # noqa: BLE001 - returned for assertions
        state["fetch_elapsed"] = time.time() - state.get("fetch_started", time.time())
        return exc, state, provider, omoney
    finally:
        os.environ.clear()
        os.environ.update(saved)
        server.shutdown()


def main() -> int:


    # 1. 429 with Retry-After is honoured and then succeeds
    t0 = time.time()
    result, state, provider, _ = run("empty_then_ok")
    elapsed = time.time() - t0
    ok = not isinstance(result, Exception) and len(result[0]) == 7 and 0.9 <= elapsed <= 3.0
    check("429 Retry-After honoured then recovers", ok,
          f"hits={state['hits']} elapsed={elapsed:.2f}s")

    # 2. Persistent 429 eventually fails without hammering
    result, state, provider, _ = run("always_429", OMONEY_FX_MAX_ATTEMPTS=3)
    check("persistent 429 bounded attempts",
          isinstance(result, Exception) and state["hits"] == 3, f"hits={state['hits']}")

    # 3. 401 fails fast, no retries
    result, state, provider, omoney_mod = run("401")
    check("401 raises auth error, single attempt",
          isinstance(result, omoney_mod.OmoneyAuthError) and state["hits"] == 1,
          f"hits={state['hits']}")

    # 4. 5xx retried then fails
    result, state, p, _ = run("500", OMONEY_FX_MAX_ATTEMPTS=2)
    check("5xx retried then errors",
          isinstance(result, Exception) and state["hits"] == 2, f"hits={state['hits']}")

    # 5. timeout respected (read timeout 1s vs server sleep 3s)
    result, state, provider, _ = run("slow", OMONEY_FX_MAX_ATTEMPTS=1)
    elapsed = state.get("fetch_elapsed", 99)
    check("read timeout enforced", isinstance(result, Exception) and elapsed < 3.0,
          f"fetch={elapsed:.2f}s {type(result).__name__}")

    # 6. non-JSON body rejected
    result, state, provider, omoney_mod = run("not_json")
    check("non-JSON rejected", isinstance(result, omoney_mod.OmoneyUnrecognizedPayload))

    # 7. missing unit never assumed
    result, state, provider, omoney_mod = run("no_unit")
    check("missing quote_currency raises (no IRR guess)",
          isinstance(result, omoney_mod.OmoneyUnrecognizedPayload))

    # 8. unavailable instruments are never published
    result, state, provider, omoney_mod = run("unavailable")
    check("unavailable excluded (no fabricated price)",
          isinstance(result, Exception) and "OMONEY_NO_PRICES" in str(result), str(result)[:50])

    # 9. stale flagged, not presented as fresh
    result, state, provider, _ = run("stale")
    rs, stale = result
    check("stale rows flagged", stale is True and all(r["status"] == "stale" for r in rs),
          f"stale={stale}")

    # 10. zero sell_price falls back to mid, never publishes 0
    result, state, provider, _ = run("zero_sell")
    rs, _ = result
    usd = next(r for r in rs if r["symbol"] == "usd_sell")
    check("zero sell_price not published", float(usd["value"]) > 0, f"usd={usd['value']}")

    # 11. non-numeric price excluded
    result, state, provider, _ = run("bad_price")
    if isinstance(result, Exception):
        ok = "OMONEY_NO_PRICES" in str(result) or "no usable" in str(result)
        check("non-numeric price never published", ok, str(result)[:50])
    else:
        rs, _ = result
        check("non-numeric price never published", all(float(r["value"]) > 0 for r in rs),
              f"{len(rs)} rows")

    print()
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED:", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
