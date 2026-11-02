#!/usr/bin/env bash
#
# Add an additional Instagram account to this server.
#
# Usage:
#   ./scripts/add-account.sh <name>
#
# Creates accounts/<name>/ with isolated state, logs, cache, and output, plus a
# .env seeded from the primary account. Then appends a docker compose service.
# Each account runs in its own container, so a fault in one cannot affect the
# others and every account keeps its own publish history and rotation state.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="${1:-}"

if [[ -z "$NAME" ]]; then
  echo "usage: $0 <name>   (lowercase letters, digits, underscores)" >&2
  exit 2
fi

if ! [[ "$NAME" =~ ^[a-z0-9_]+$ ]]; then
  echo "error: name must match ^[a-z0-9_]+\$ (got '$NAME')" >&2
  exit 2
fi

if [[ "$NAME" == "omoney" || "$NAME" == "primary" ]]; then
  echo "error: '$NAME' is reserved for the primary account" >&2
  exit 2
fi

ACCOUNT_DIR="$ROOT_DIR/accounts/$NAME"
ENV_FILE="$ACCOUNT_DIR/.env"
SERVICE="omoney-rates-bot-$NAME"

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "error: $ROOT_DIR/.env not found; run from the bot directory" >&2
  exit 1
fi

mkdir -p "$ACCOUNT_DIR"/{data,cache,output,logs}

if [[ -f "$ENV_FILE" ]]; then
  echo "note: $ENV_FILE already exists, keeping it"
else
  python3 - "$ROOT_DIR/.env" "$ENV_FILE" "$NAME" <<'PY'
import pathlib, sys

source, target, name = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]

# Values that must be unique per account.
override = {
    "INSTAGRAM_ACCESS_TOKEN": "",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID": "",
    "TELEGRAM_CHANNEL": "",
    "R2_KEY_PREFIX": name,
    "ALERT_TELEGRAM_CHAT": "",
}

lines, seen = [], set()
for line in source.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0]
    if key in override:
        lines.append(f"{key}={override[key]}")
        seen.add(key)
    else:
        lines.append(line)
for key, value in override.items():
    if key not in seen:
        lines.append(f"{key}={value}")

target.write_text("\n".join(lines) + "\n")
PY
  chmod 600 "$ENV_FILE"
fi

python3 - "$ROOT_DIR/docker-compose.yml" "$NAME" "$SERVICE" <<'PY'
import pathlib, sys

compose, name, service = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = compose.read_text(encoding="utf-8")

if f"container_name: {service}" in text:
    print(f"note: compose service {service} already exists")
    raise SystemExit(0)

block = f"""
  {service}:
    <<: *omoney-bot
    container_name: {service}
    env_file:
      - accounts/{name}/.env
    volumes:
      - ./accounts/{name}/data:/app/data:ro
      - ./accounts/{name}/cache:/app/cache
      - ./accounts/{name}/output:/app/output
      - ./accounts/{name}/logs:/app/logs
"""
compose.write_text(text.rstrip("\n") + "\n" + block, encoding="utf-8")
print(f"added compose service {service}")
PY

if ! grep -q "^R2_KEY_PREFIX=" "$ENV_FILE"; then
  echo "R2_KEY_PREFIX=$NAME" >> "$ENV_FILE"
fi

cat <<EOF

Created accounts/$NAME with its own logs, output, cache, and R2 prefix "$NAME/".

Next steps:
  1. Fill these 4 values in accounts/$NAME/.env:
       INSTAGRAM_ACCESS_TOKEN=        (IGAA... or EAB... token for that account)
       INSTAGRAM_BUSINESS_ACCOUNT_ID= (that account's IG business id)
       TELEGRAM_CHANNEL=              (that account's channel)
       ALERT_TELEGRAM_CHAT=           (where alerts should go)
  2. Verify the token before starting:
       docker compose run --rm $SERVICE python -m app.main --instagram-token-status
  3. Start the account:
       docker compose up -d --build

The account's publish times come from PUBLISH_TIMES / CONTENT_PUBLISH_TIMES in
its own .env, so it can run on a completely different schedule.
EOF
