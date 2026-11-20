#!/usr/bin/env bash
#
# Securely store the Omoney FX API key for this deployment.
#
# Usage:
#   ./scripts/set-omoney-key.sh            # writes /opt/omoney-rates-bot/.env
#   ENV_FILE=accounts/second/.env ./scripts/set-omoney-key.sh
#
# The key is read with echo disabled, is never passed as a command-line
# argument (so it does not appear in shell history or the process table), is
# never echoed back, and is written straight to the environment file with 0600
# permissions. Only a masked confirmation is printed.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found" >&2
  exit 1
fi

if [[ -t 0 ]]; then
  printf 'Enter Omoney FX API key (input hidden): ' >&2
  IFS= read -rs OMONEY_KEY
  printf '\n' >&2
else
  # Non-interactive: read one line from stdin, still never echoed.
  IFS= read -r OMONEY_KEY
fi

# Strip accidental whitespace/newlines without echoing the value.
OMONEY_KEY="${OMONEY_KEY//[[:space:]]/}"

if [[ -z "$OMONEY_KEY" ]]; then
  echo "error: empty key, nothing written" >&2
  exit 1
fi

if [[ ${#OMONEY_KEY} -lt 16 ]]; then
  echo "error: key looks too short (${#OMONEY_KEY} chars), nothing written" >&2
  exit 1
fi

python3 - "$ENV_FILE" "$OMONEY_KEY" <<'PY'
import pathlib, sys

env_path, key = pathlib.Path(sys.argv[1]), sys.argv[2]

updates = {
    "OMONEY_FX_BASE_URL": "https://fx.omoney.online",
    "OMONEY_FX_API_KEY": key,
}

lines = env_path.read_text(encoding="utf-8").splitlines()
out, seen = [], set()
for line in lines:
    name = line.split("=", 1)[0]
    if name in updates:
        out.append(f"{name}={updates[name]}")
        seen.add(name)
    else:
        out.append(line)
for name, value in updates.items():
    if name not in seen:
        out.append(f"{name}={value}")

env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY

chmod 600 "$ENV_FILE"
unset OMONEY_KEY

LEN=$(awk -F= '/^OMONEY_FX_API_KEY=/{print length($2)}' "$ENV_FILE")
TAIL=$(awk -F= '/^OMONEY_FX_API_KEY=/{print substr($2, length($2)-3)}' "$ENV_FILE")
PROVIDER=$(awk -F= '/^CURRENCY_PROVIDER=/{print $2}' "$ENV_FILE")
PROVIDER="${PROVIDER:-navasan}"

cat <<EOF

Stored in $ENV_FILE (mode 600):
  OMONEY_FX_API_KEY = ****${TAIL}  (${LEN} chars)

CURRENCY_PROVIDER is still '$PROVIDER', so live publishing is unchanged.

To validate without touching production:
  docker compose run --rm -e CURRENCY_PROVIDER=omoney omoney-rates-bot \\
    python -m app.main --fetch-test

To cut over after validation is approved, set CURRENCY_PROVIDER=omoney in
$ENV_FILE and run: docker compose up -d --force-recreate
EOF
