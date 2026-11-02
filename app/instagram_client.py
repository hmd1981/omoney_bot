from __future__ import annotations

import requests
import time

from app.instagram_token import GraphError, inspect_access_token


class InstagramAuthError(RuntimeError):
    """Raised when Meta rejects the access token itself (expired or invalid)."""


class InstagramClient:
    def __init__(
        self,
        business_account_id: str,
        access_token: str,
        api_version: str = "v23.0",
        base_url: str = "https://graph.facebook.com",
    ) -> None:
        self._business_account_id = business_account_id
        self._access_token = access_token
        self._base_url = f"{base_url.rstrip('/')}/{api_version}"

    def publish_image(self, image_url: str, caption: str) -> str:
        self.validate_account_access()
        container_id = self._create_image_container(image_url=image_url, caption=caption)
        self._wait_for_container(container_id)
        return self._publish_container(container_id)

    def validate_account_access(self) -> None:
        response = requests.get(
            f"{self._base_url}/{self._business_account_id}",
            params={
                "fields": "id,username,media_count",
                "access_token": self._access_token,
            },
            timeout=30,
        )
        if not response.ok:
            raise self._error_from_response(response, stage="account check")

    def _error_from_response(self, response: requests.Response, *, stage: str) -> RuntimeError:
        error = GraphError.from_response(response)
        if error.is_auth_error:
            return InstagramAuthError(
                "INSTAGRAM_TOKEN_INVALID: Meta rejected INSTAGRAM_ACCESS_TOKEN as expired or "
                f"invalid during {stage}. Generate a new long-lived token and update "
                f"INSTAGRAM_ACCESS_TOKEN, then restart the bot. Meta response: {error.describe()}"
            )
        return RuntimeError(
            "INSTAGRAM_ACCOUNT_NOT_ACCESSIBLE: token cannot read "
            f"INSTAGRAM_BUSINESS_ACCOUNT_ID={self._business_account_id} during {stage}. "
            "Use the Instagram Business/Creator account ID connected to a Facebook Page "
            "that this token can access, and grant instagram_basic plus "
            f"instagram_content_publish permissions. Meta response: {error.describe()}"
        )

    def _create_image_container(self, image_url: str, caption: str) -> str:
        response = requests.post(
            f"{self._base_url}/{self._business_account_id}/media",
            data={
                "image_url": image_url,
                "caption": caption,
                "access_token": self._access_token,
            },
            timeout=30,
        )
        if not response.ok:
            raise self._error_from_response(response, stage="media container creation")
        payload = response.json()
        container_id = str(payload.get("id", "")).strip()
        if not container_id:
            raise RuntimeError("Instagram media container response did not include id")
        return container_id

    def _wait_for_container(self, creation_id: str, attempts: int = 12, delay_seconds: int = 5) -> None:
        last_status = ""
        for attempt in range(1, attempts + 1):
            response = requests.get(
                f"{self._base_url}/{creation_id}",
                params={
                    "fields": "status_code,status",
                    "access_token": self._access_token,
                },
                timeout=30,
            )
            if not response.ok:
                raise self._error_from_response(response, stage="media status polling")
            payload = response.json()
            last_status = str(payload.get("status_code") or payload.get("status") or "").strip()
            if last_status in {"FINISHED", "PUBLISHED"}:
                return
            if last_status in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram media container failed before publish: {payload}")
            if attempt < attempts:
                time.sleep(delay_seconds)
        raise RuntimeError(f"Instagram media container was not ready after {attempts * delay_seconds}s: {last_status}")

    def _publish_container(self, creation_id: str) -> str:
        response = requests.post(
            f"{self._base_url}/{self._business_account_id}/media_publish",
            data={
                "creation_id": creation_id,
                "access_token": self._access_token,
            },
            timeout=30,
        )
        if not response.ok:
            raise self._error_from_response(response, stage="media publish")
        payload = response.json()
        media_id = str(payload.get("id", "")).strip()
        if not media_id:
            raise RuntimeError("Instagram publish response did not include id")
        return media_id

    def inspect_token(self, *, app_id: str = "", app_secret: str = ""):
        return inspect_access_token(
            access_token=self._access_token,
            business_account_id=self._business_account_id,
            app_id=app_id,
            app_secret=app_secret,
        )
