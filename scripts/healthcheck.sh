#!/usr/bin/env bash
# One-command health check for the Omoney rates bot.
#
# Read-only: never publishes, never changes configuration, never restarts.
# Prints the API key fingerprint only -- never the key itself.
#
# Usage: ./scripts/healthcheck.sh
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

if ! docker compose ps --format '{{.Status}}' omoney-rates-bot 2>/dev/null | grep -q "Up"; then
  echo "FAIL: container omoney-rates-bot is not running"
  exit 1
fi

# A throwaway container keeps the running service untouched while reusing its
# exact image and environment.
docker compose run --rm -T \
  -e PYTHONPATH=/app \
  -v "$PWD/scripts:/app/scripts:ro" \
  omoney-rates-bot python /app/scripts/healthcheck.py 2>&1 |
  grep -vE "^( Container|\[?\+?\]? ?Container)"
exit "${PIPESTATUS[0]}"
