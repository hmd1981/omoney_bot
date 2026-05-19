from pathlib import Path

import requests


class TelegramClient:
    def __init__(self, bot_token: str) -> None:
        self._base_url = f"https://api.telegram.org/bot{bot_token}"

    def send_photo(self, channel: str, image_path: Path, caption: str = "") -> None:
        with image_path.open("rb") as image_file:
            response = requests.post(
                f"{self._base_url}/sendPhoto",
                data={"chat_id": channel, "caption": caption},
                files={"photo": image_file},
                timeout=30,
            )
        response.raise_for_status()
