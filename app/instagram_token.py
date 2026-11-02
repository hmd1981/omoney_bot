from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os

import requests

DEFAULT_BASE_URL = "https://graph.facebook.com"
DEFAULT_API_VERSION = "v23.0"
DEFAULT_REFRESH_URL = "https://graph.instagram.com/refresh_access_token"

# Meta error codes that mean the token itself is dead or rejected, as opposed to
# a permission/account configuration problem.
AUTH_ERROR_CODES = frozenset({102, 190, 463, 467})
AUTH_MESSAGE_MARKERS = (
    "session has expired",
    "token has expired",
    "invalid oauth access token",
    "access token could not be decrypted",
    "the access token is invalid",
)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def token_prefix_family(access_token: str) -> str:
    """Classify a Meta token by prefix.

    ``IGAA`` tokens come from Instagram API with Instagram Login and only work
    on graph.instagram.com. ``EAA`` tokens come from Facebook Login / Business
    Manager system users and only work on graph.facebook.com.
    """
    token = (access_token or "").strip()
    if token.startswith("IGAA") or token.startswith("IGQV"):
        return "instagram_login"
    if token.startswith("EA"):
        return "facebook"
    return "unknown"


def endpoint_mismatch(access_token: str, base_url: str) -> str:
    """Return a human-readable problem when token family and API host disagree."""
    family = token_prefix_family(access_token)
    host = (base_url or "").lower()
    on_instagram_host = "graph.instagram.com" in host
    on_facebook_host = "graph.facebook.com" in host
    if family == "instagram_login" and on_facebook_host:
        return (
            "token starts with IGAA (Instagram Login) but INSTAGRAM_API_BASE_URL points at "
            "graph.facebook.com; set it to https://graph.instagram.com"
        )
    if family == "facebook" and on_instagram_host:
        return (
            "token starts with EAA (Facebook/Business Manager) but INSTAGRAM_API_BASE_URL points at "
            "graph.instagram.com; either set it to https://graph.facebook.com or use an IGAA token"
        )
    return ""


def api_base_url() -> str:
    return _env("INSTAGRAM_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def api_version() -> str:
    return _env("INSTAGRAM_API_VERSION", DEFAULT_API_VERSION)


def graph_root() -> str:
    return f"{api_base_url()}/{api_version()}"


def debug_base_url() -> str:
    """debug_token lives on the Facebook Graph host, not graph.instagram.com."""
    return _env("INSTAGRAM_DEBUG_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def debug_root() -> str:
    return f"{debug_base_url()}/{api_version()}"


@dataclass(frozen=True)
class GraphError:
    code: int | None = None
    subcode: int | None = None
    type: str = ""
    message: str = ""
    raw: str = ""

    @classmethod
    def from_payload(cls, payload: object, raw: str = "") -> "GraphError":
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return cls(raw=raw)

        def _as_int(value: object) -> int | None:
            try:
                return int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None

        return cls(
            code=_as_int(error.get("code")),
            subcode=_as_int(error.get("error_subcode")),
            type=str(error.get("type") or ""),
            message=str(error.get("message") or ""),
            raw=raw,
        )

    @classmethod
    def from_response(cls, response: requests.Response) -> "GraphError":
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return cls.from_payload(payload, raw=response.text[:600])

    @property
    def is_auth_error(self) -> bool:
        if self.code in AUTH_ERROR_CODES:
            return True
        lowered = self.message.lower()
        return any(marker in lowered for marker in AUTH_MESSAGE_MARKERS)

    def describe(self) -> str:
        parts = []
        if self.type:
            parts.append(self.type)
        if self.code is not None:
            parts.append(f"code={self.code}")
        if self.subcode:
            parts.append(f"subcode={self.subcode}")
        label = " ".join(parts)
        if self.message:
            return f"{self.message} ({label})" if label else self.message
        return label or self.raw or "unknown Meta error"


@dataclass(frozen=True)
class InstagramTokenStatus:
    configured: bool
    valid: bool
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = ()
    source: str = ""
    error: str = ""
    error_code: int | None = None

    @property
    def days_remaining(self) -> float | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - datetime.now(timezone.utc)).total_seconds() / 86400.0

    @property
    def never_expires(self) -> bool:
        return self.valid and self.expires_at is None

    def expiring_within(self, days: float) -> bool:
        remaining = self.days_remaining
        return remaining is not None and 0 <= remaining <= days

    def expires_text(self) -> str:
        if self.expires_at is None:
            return "unknown" if self.valid else "n/a"
        return self.expires_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def days_remaining_text(self) -> str:
        remaining = self.days_remaining
        if remaining is None:
            return "unknown"
        return f"{remaining:.1f}"


def _parse_expires_at(value: object) -> datetime | None:
    try:
        epoch = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc)


def _debug_token(
    access_token: str,
    app_id: str,
    app_secret: str,
) -> InstagramTokenStatus | None:
    """Inspect the token with Meta's debug_token endpoint.

    Returns None when the inspection itself could not run (missing or rejected
    app credentials), so the caller can fall back to probing the account.
    """
    if not app_id or not app_secret:
        return None
    try:
        response = requests.get(
            f"{debug_root()}/debug_token",
            params={
                "input_token": access_token,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout=20,
        )
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None

    is_valid = bool(data.get("is_valid"))
    error_payload = data.get("error") or {}
    error_message = ""
    error_code: int | None = None
    if isinstance(error_payload, dict):
        error_message = str(error_payload.get("message") or "")
        try:
            error_code = int(error_payload.get("code"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            error_code = None
    scopes_value = data.get("scopes")
    scopes = tuple(str(item) for item in scopes_value) if isinstance(scopes_value, list) else ()
    return InstagramTokenStatus(
        configured=True,
        valid=is_valid,
        expires_at=_parse_expires_at(data.get("expires_at")),
        scopes=scopes,
        source="debug_token",
        error="" if is_valid else (error_message or "token is not valid"),
        error_code=error_code,
    )


def _probe_account(access_token: str, business_account_id: str) -> InstagramTokenStatus:
    if not business_account_id:
        return InstagramTokenStatus(
            configured=True,
            valid=False,
            source="probe",
            error="INSTAGRAM_BUSINESS_ACCOUNT_ID is not configured",
        )
    try:
        response = requests.get(
            f"{graph_root()}/{business_account_id}",
            params={"fields": "id,username", "access_token": access_token},
            timeout=20,
        )
    except requests.RequestException as exc:
        return InstagramTokenStatus(
            configured=True,
            valid=False,
            source="probe",
            error=f"could not reach Meta: {exc}",
        )
    if response.ok:
        return InstagramTokenStatus(configured=True, valid=True, source="probe")
    error = GraphError.from_response(response)
    return InstagramTokenStatus(
        configured=True,
        valid=False,
        source="probe",
        error=error.describe(),
        error_code=error.code,
    )


def inspect_access_token(
    access_token: str,
    business_account_id: str = "",
    app_id: str = "",
    app_secret: str = "",
) -> InstagramTokenStatus:
    """Return the health of the configured Instagram access token.

    Prefers Meta's debug_token endpoint (gives the real expiry date) and falls
    back to probing the business account when app credentials are unavailable.
    """
    token = (access_token or "").strip()
    if not token:
        return InstagramTokenStatus(
            configured=False,
            valid=False,
            error="INSTAGRAM_ACCESS_TOKEN is not configured",
        )
    mismatch = endpoint_mismatch(token, api_base_url())
    if mismatch:
        return InstagramTokenStatus(
            configured=True,
            valid=False,
            source="config",
            error=f"CONFIGURATION_MISMATCH: {mismatch}",
        )
    status = _debug_token(token, (app_id or "").strip(), (app_secret or "").strip())
    if status is not None:
        return status
    return _probe_account(token, (business_account_id or "").strip())


@dataclass(frozen=True)
class TokenRefreshResult:
    ok: bool
    access_token: str = ""
    expires_at: datetime | None = None
    error: str = ""


def refresh_long_lived_token(
    access_token: str,
    app_id: str = "",
    app_secret: str = "",
) -> TokenRefreshResult:
    """Extend a still-valid long-lived token by another ~60 days.

    Tries the Instagram-login refresh endpoint first, then the Facebook
    fb_exchange_token flow when app credentials are configured.
    """
    token = (access_token or "").strip()
    if not token:
        return TokenRefreshResult(ok=False, error="INSTAGRAM_ACCESS_TOKEN is not configured")

    refresh_url = _env("INSTAGRAM_REFRESH_URL", DEFAULT_REFRESH_URL)
    try:
        response = requests.get(
            refresh_url,
            params={"grant_type": "ig_refresh_token", "access_token": token},
            timeout=30,
        )
        if response.ok:
            payload = response.json()
            new_token = str(payload.get("access_token") or "").strip()
            if new_token:
                try:
                    expires_in = int(payload.get("expires_in") or 0)
                except (TypeError, ValueError):
                    expires_in = 0
                expires_at = (
                    datetime.fromtimestamp(
                        datetime.now(timezone.utc).timestamp() + expires_in, tz=timezone.utc
                    )
                    if expires_in > 0
                    else None
                )
                return TokenRefreshResult(ok=True, access_token=new_token, expires_at=expires_at)
    except requests.RequestException as exc:
        ig_error = f"request failed: {exc}"
    else:
        ig_error = GraphError.from_response(response).describe() if not response.ok else "no access_token returned"

    if not (app_id and app_secret):
        return TokenRefreshResult(ok=False, error=f"Instagram refresh failed: {ig_error}")

    try:
        response = requests.get(
            f"{graph_root()}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": token,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        return TokenRefreshResult(ok=False, error=f"request failed: {exc}")
    if not response.ok:
        return TokenRefreshResult(
            ok=False, error=f"Facebook refresh failed: {GraphError.from_response(response).describe()}"
        )
    payload = response.json()
    new_token = str(payload.get("access_token") or "").strip()
    if not new_token:
        return TokenRefreshResult(ok=False, error="Facebook refresh returned no access_token")
    try:
        expires_in = int(payload.get("expires_in") or 0)
    except (TypeError, ValueError):
        expires_in = 0
    expires_at = (
        datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + expires_in, tz=timezone.utc)
        if expires_in > 0
        else None
    )
    return TokenRefreshResult(ok=True, access_token=new_token, expires_at=expires_at)
