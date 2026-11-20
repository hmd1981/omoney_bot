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

## Currency rate provider

Rates come from a pluggable provider selected with `CURRENCY_PROVIDER`:

| Value | Provider | Notes |
|---|---|---|
| `navasan` | Navasan (legacy) | current default |
| `omoney` | Omoney FX API | `https://fx.omoney.online` |

```env
CURRENCY_PROVIDER=navasan          # switch to omoney to cut over
OMONEY_FX_BASE_URL=https://fx.omoney.online
OMONEY_FX_API_KEY=                 # set with scripts/set-omoney-key.sh
```

### Storing the API key securely

```bash
./scripts/set-omoney-key.sh
```

Reads the key with input hidden, writes it to `.env` with mode `0600`, and
prints only a masked confirmation (`****1234`). It does **not** change
`CURRENCY_PROVIDER`, so live publishing keeps using the current provider.

### Validating Omoney FX without touching production

```bash
docker compose run --rm -e CURRENCY_PROVIDER=omoney omoney-rates-bot \
  python -m app.main --fetch-test
```

This exercises the real endpoint and the symbol mapping while the scheduler
keeps running on the current provider. `--fetch-test` reports
`provider=`, `source=live|cache`, `count=`, and `symbols=`.

### Verified symbol mapping

Checked against live `GET /v1/instruments` (15 instruments) and
`GET /v1/prices`:

| App symbol | Omoney instrument | Price field | Unit |
|---|---|---|---|
| `usd_sell` | `USD` | `sell_price` | IRT |
| `cad` | `CAD` | `price` | IRT |
| `aed_sell` | `AED` | `sell_price` | IRT |
| `try` | `TRY` | `price` | IRT |
| `omr` | `OMR` | `price` | IRT |
| `btc` | `BTC` | `price` | IRT |
| `usdt` | `USDT` | `price` | IRT |
| `18ayar` | **none** | — | — |

`usd_sell` / `aed_sell` use `sell_price` because the legacy symbols represent
the customer sell rate; everything else uses the mid `price`. If `sell_price`
is missing or `0` the adapter falls back to the mid price rather than
publishing a zero.

### Units: IRT (toman), not IRR

The Omoney API quotes in **IRT (toman)**, and the adapter labels the image with
the API's own `quote_currency`. Note that this differs from the old Navasan
output, which printed toman values under an `IRR` label: the frozen Navasan
snapshot (`usd_sell=268,600`) and Omoney's live `USD` (`271,150` IRT) agree to
within market movement, while the AED/USD ratio comes out at `3.6726` against
the `3.6725` peg. So the numbers were always toman and only the unit label was
wrong. `GET /v1/prices?quote=IRR` is available if rial is ever required, but the
API's `unit` text string stays "Toman per..." regardless, so `quote_currency`
is the field to trust.

### Gold is not available

There is no gram-gold instrument. `XAU` is quoted in USD per troy ounce and
currently returns `price: null, status: "unavailable"`; `SEKKEH`/`BAHAR` are
whole coins. Mapping `18ayar` to any of them would mislabel a different
product, so it is deliberately unmapped and that row is omitted. Add an
instrument to `OMONEY_SYMBOLS` once a matching one exists.

### Behaviour

- Bounded timeouts: `OMONEY_FX_CONNECT_TIMEOUT` (5s) and
  `OMONEY_FX_READ_TIMEOUT` (15s).
- Up to `OMONEY_FX_MAX_ATTEMPTS` (3) attempts with capped backoff;
  `Retry-After` is honoured on 429, capped at `OMONEY_FX_MAX_RETRY_SLEEP`.
- 401 fails fast and never retries. A rejected key raises
  `OMONEY_FX_UNAUTHORIZED`.
- Prices older than `OMONEY_FX_MAX_PRICE_AGE_MINUTES` (240), or flagged
  stale/unavailable by the API, are treated as stale: the image shows the
  "Last cached update" note rather than presenting them as fresh.
- A missing unit/quote field raises rather than assuming IRR — rial and toman
  are never silently substituted.
- Snapshots are cached in `cache/last_rates_omoney.json`, separate from the
  Navasan cache so the two providers' units can never mix.
- `OMONEY_SYMBOLS` overrides the mapping as app_symbol=INSTRUMENT[:field]; an unmatched
  instrument raises `OMONEY_INSTRUMENT_UNKNOWN` and lists what the API offers.

### Rollback

Set `CURRENCY_PROVIDER=navasan` and run `docker compose up -d --force-recreate`.
The Navasan code path and its cache are untouched.

## Health and logs

One command checks the whole pipeline (read-only — it never publishes,
changes config, or restarts anything):

```bash
./scripts/healthcheck.sh
```

It verifies the container, provider, key presence, an authenticated
`/v1/prices` call, the app's own fetch path, R2 storage, the Instagram token,
and the publish schedule. The API key is reported as a SHA-256 fingerprint and
last four characters only.

```bash
docker compose ps
docker compose logs --tail=100 omoney-rates-bot
```

### Automated alerts

Scheduled runs alert the operator chat when something would otherwise fail
silently:

| Alert | When | Cooldown |
|---|---|---|
| `rates-from-cache` | A run publishes the cached snapshot instead of live data (includes cache age) | 6h |
| `rate-generation-failed` | Rate fetch or image generation raised | 1h |
| `instagram-token-invalid` / `-expiring-*` | Token rejected or nearing expiry | 12h / 24h |
| `instagram-publish-failed-*` | An Instagram post failed | 1h |

Cooldowns keep a persistent fault from spamming the operator on every run.
Alerts go to `ALERT_TELEGRAM_CHAT` (the operator), never to the public channel.

## Files

- Generated images: `output/`
- Logs: `logs/`
- Fallback cache: `cache/last_rates.json`
