#!/usr/bin/env sh
set -eu

GUARDIAN_URL="${GUARDIAN_URL:-http://127.0.0.1:8000}"

payload="$(cat)"

curl -fsS \
  -H "Content-Type: application/json" \
  -X POST \
  --data "$payload" \
  "$GUARDIAN_URL/events/prompt" >/dev/null
