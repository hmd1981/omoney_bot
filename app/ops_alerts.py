from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path

from app.telegram_client import TelegramClient

log = logging.getLogger("omoney-rates-bot.alerts")

ALERT_STATE_FILE = Path("/app/logs/alert-state.json")


def alert_chat() -> str:
    return os.getenv("ALERT_TELEGRAM_CHAT", "").strip() or os.getenv("TELEGRAM_ALERT_CHAT", "").strip()


def _load_state() -> dict[str, str]:
    if not ALERT_STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _save_state(state: dict[str, str]) -> None:
    try:
        ALERT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        log.warning("alert_state_write_failed %s", exc)


def _last_sent(state: dict[str, str], key: str) -> datetime | None:
    raw = state.get(key)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def send_alert(*, key: str, message: str, cooldown_hours: float | None = None) -> bool:
    """Send an operational alert to Telegram, logging it when unconfigured.

    ``cooldown_hours`` suppresses repeats of the same ``key`` so a broken token
    cannot spam the operator on every scheduled run.
    """
    now = datetime.now(timezone.utc)
    state = _load_state()
    if cooldown_hours is not None:
        last = _last_sent(state, key)
        if last is not None and now - last < timedelta(hours=cooldown_hours):
            log.info("alert_suppressed key=%s", key)
            return False

    chat = alert_chat()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not chat or not token:
        log.critical("alert_not_delivered key=%s reason=ALERT_TELEGRAM_CHAT_not_set message=%s", key, message)
        return False

    try:
        TelegramClient(token).send_message(chat=chat, text=message)
    except Exception as exc:  # noqa: BLE001 - alerting must never break publishing
        log.error("alert_delivery_failed key=%s error=%s", key, exc)
        return False

    state[key] = now.isoformat()
    _save_state(state)
    log.warning("alert_sent key=%s", key)
    return True
