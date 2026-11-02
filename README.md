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

- `INSTAGRAM_TOKEN_INVALID` means the access token itself expired or was revoked. Long-lived Instagram tokens last about 60 days. Generate a new token and update `INSTAGRAM_ACCESS_TOKEN`, then restart the bot.
- `INSTAGRAM_IMAGE_PUBLIC_URL_NOT_REACHABLE` means the configured public URL does not return HTTP 200.
- `INSTAGRAM_IMAGE_PUBLIC_URL_NOT_IMAGE` means the URL is reachable but does not return an image content type.
- `INSTAGRAM_ACCOUNT_NOT_ACCESSIBLE` means the token is valid but cannot read the configured Instagram business account. Verify the account ID, Facebook Page connection, and granted Meta permissions.

## Instagram token health

Long-lived Instagram tokens expire after roughly 60 days, which silently stops Instagram publishing while Telegram keeps working. The bot now checks the token daily and alarms on expiry.

```bash
# Validity, expiry date, remaining days, granted scopes
docker compose run --rm omoney-rates-bot python -m app.main --instagram-token-status

# Extend a still-valid token by another ~60 days; prints the new token to paste into .env
docker compose run --rm omoney-rates-bot python -m app.main --instagram-token-refresh
```

Alerting configuration (`.env`):

```env
# Private chat/group that receives operational alarms. Leave empty to only log.
ALERT_TELEGRAM_CHAT=
# Warn this many days before the token expires.
INSTAGRAM_TOKEN_WARN_DAYS=7
# Daily preflight time in TIMEZONE.
INSTAGRAM_TOKEN_CHECK_TIME=09:00
INSTAGRAM_APP_ID=
INSTAGRAM_APP_SECRET=
```

`INSTAGRAM_APP_ID` and `INSTAGRAM_APP_SECRET` are optional but recommended: they let the bot read the token's real expiry date through Meta's `debug_token` endpoint instead of inferring it.

Alerts are sent when the token is invalid, when it expires within `INSTAGRAM_TOKEN_WARN_DAYS`, and when any Instagram publish fails. Repeats are cooldown-limited in `logs/alert-state.json`.

## Multiple Instagram accounts

Each account runs in **its own container** with its own state, logs, and R2 key
prefix. Isolation is deliberate: a bad token or failed post in one account
cannot affect the others, and each account keeps independent publish history
and caption rotation.

Add an account:

```bash
./scripts/add-account.sh second
```

That creates `accounts/second/` (data, cache, output, logs) seeded with a
`.env`, adds a compose service, and sets `R2_KEY_PREFIX=second`. Fill four
values in `accounts/second/.env`:

```env
INSTAGRAM_ACCESS_TOKEN=
INSTAGRAM_BUSINESS_ACCOUNT_ID=
TELEGRAM_CHANNEL=
ALERT_TELEGRAM_CHAT=
```

Verify the token, then start it:

```bash
docker compose run --rm omoney-rates-bot-second python -m app.main --instagram-token-status
docker compose up -d --build
```

Each account has its own `PUBLISH_TIMES` and `CONTENT_PUBLISH_TIMES`, so
accounts can run on completely different schedules.

R2 key layout:

| Account | Instagram image | Rate PNG | Content PNG |
|---|---|---|---|
| primary (`R2_KEY_PREFIX=`) | `instagram/latest.jpg` | `latest.png` | `content/latest.png` |
| secondary (`R2_KEY_PREFIX=second`) | `second/instagram/latest.jpg` | `second/latest.png` | `second/content/latest.png` |

Keep the primary account's prefix empty: the public website points at
`latest.png` and `instagram/latest.jpg`.

### Capacity

Measured on this server (2 vCPU, 3.7 GB RAM): one rate post costs ~4.5 s and
~30 MB peak RSS; an idle bot uses 34 MB. Meta allows **100 published posts per
24 hours per Instagram account** (check with
`GET /{ig-user-id}/content_publishing_limit`). At 3 posts/day per account the
hardware is not the constraint; the per-account Meta quota is.

Monitor all accounts:

```bash
docker compose ps
docker compose logs --tail=50 omoney-rates-bot-second
```

## Health and logs

```bash
docker compose ps
docker compose logs --tail=100 omoney-rates-bot
```

## Files

- Generated images: `output/`
- Logs: `logs/`
- Fallback cache: `cache/last_rates.json`
