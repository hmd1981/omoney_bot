# OMoney Rates Bot

Lightweight Telegram image poster for daily Iranian exchange-rate updates.

## Safety profile

- Outbound-only Telegram API traffic.
- No published ports.
- No host networking.
- Separate Compose project under `/opt/omoney-rates-bot`.

## Setup

1. Copy `.env.example` to `.env`.
2. Fill `BOT_TOKEN` and `TELEGRAM_CHANNEL`.
3. Set `NAVASAN_API_KEY`.
4. Optional: customize `NAVASAN_SYMBOLS` and `PUBLISH_TIMES`.
5. Optional: configure Instagram publishing with:
   - `INSTAGRAM_ENABLED=true`
   - `INSTAGRAM_BUSINESS_ACCOUNT_ID`
   - `INSTAGRAM_ACCESS_TOKEN`
   - `INSTAGRAM_API_BASE_URL`
   - `INSTAGRAM_IMAGE_PUBLIC_URL`
   - `R2_ENDPOINT_URL`
   - `R2_BUCKET`
   - `R2_ACCESS_KEY_ID`
   - `R2_SECRET_ACCESS_KEY`
   - `R2_PUBLIC_BASE_URL`
6. Start the service:

```bash
docker compose up -d
```

## Manual publish test

```bash
docker compose run --rm omoney-rates-bot python -m app.main --fetch-test
docker compose run --rm omoney-rates-bot python -m app.main --send-now
```

## Preview and manual send

Generate a preview only:

```bash
docker compose run --rm omoney-rates-bot python -m app.main --preview-only
```

Generate the latest preview and send it to Telegram:

```bash
docker compose run --rm omoney-rates-bot python -m app.main --preview-send
```

Send the newest existing PNG from `output/` without regenerating:

```bash
docker compose run --rm omoney-rates-bot python -m app.main --send-latest
```

Generate and publish branded content posts:

```bash
docker compose run --rm omoney-rates-bot python -m app.main --content-preview
docker compose run --rm omoney-rates-bot python -m app.main --content-send
docker compose run --rm omoney-rates-bot python -m app.main --content-schedule-status
```

Optional OpenAI-backed content image generation:

```bash
docker compose run --rm omoney-rates-bot python -m app.main --content-ai-preview
docker compose run --rm omoney-rates-bot python -m app.main --content-ai-send
```

OpenAI content generation is optional. Set these values in `.env` to enable it:

```env
CONTENT_IMAGE_PROVIDER=openai
CONTENT_AI_IMAGE_ENABLED=true
OPENAI_API_KEY=
OPENAI_IMAGE_MODEL=gpt-image-2
```

If OpenAI is not configured, scheduled content posts keep using the local Pillow generator.

Publish one Instagram feed test post from the current public preview image URL:

```bash
docker compose run --rm omoney-rates-bot python -m app.main --instagram-test
```

`--instagram-test` generates the preview, uploads it to R2 as `latest.png`, verifies the public URL, then asks Instagram to publish that image. Instagram reads the image from the public URL; it does not receive the local PNG file directly.

Instagram troubleshooting:

- `INSTAGRAM_IMAGE_PUBLIC_URL_NOT_REACHABLE` means the configured public URL does not return HTTP 200.
- `INSTAGRAM_IMAGE_PUBLIC_URL_NOT_IMAGE` means the URL is reachable but does not return an image content type.
- `INSTAGRAM_ACCOUNT_NOT_ACCESSIBLE` means the token cannot read the configured Instagram business account. Verify the account ID, Facebook Page connection, and granted Meta permissions.

## Health and logs

```bash
docker compose ps
docker compose logs --tail=100 omoney-rates-bot
```

## Files

- Generated images: `output/`
- Logs: `logs/`
- Fallback cache: `cache/last_rates.json`
