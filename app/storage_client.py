from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

import boto3
from botocore.config import Config


class R2StorageClient:
    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        public_base_url: str,
    ) -> None:
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/") + "/"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def upload_png(self, image_path: Path, key: str) -> str:
        if not image_path.exists() or not image_path.is_file():
            raise FileNotFoundError(f"image file does not exist: {image_path}")
        normalized_key = key.lstrip("/")
        self._client.upload_file(
            str(image_path),
            self._bucket,
            normalized_key,
            ExtraArgs={
                "ContentType": "image/png",
                "CacheControl": "public, max-age=60",
            },
        )
        return urljoin(self._public_base_url, normalized_key)
