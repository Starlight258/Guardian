#!/usr/bin/env sh
set -eu

GUARDIAN_URL="${GUARDIAN_URL:-http://127.0.0.1:8000}"

payload="${GUARDIAN_SESSION_CHECKPOINT_PAYLOAD:-}"
if [ -z "$payload" ]; then
  payload="$(cat)"
fi

if [ -z "$(printf '%s' "$payload" | tr -d '[:space:]')" ]; then
  exit 0
fi

payload="$(
  GUARDIAN_SESSION_ID="${GUARDIAN_SESSION_ID:-session-end}" \
  GUARDIAN_SESSION_METADATA="${GUARDIAN_SESSION_METADATA:-}" \
  SESSION_CHECKPOINT_PAYLOAD="$payload" \
  python3 -c 'import json, os, sys
raw = os.environ["SESSION_CHECKPOINT_PAYLOAD"].strip()
if not raw:
    raise SystemExit(0)

session_id = os.environ["GUARDIAN_SESSION_ID"].strip() or "session-end"
metadata_raw = os.environ.get("GUARDIAN_SESSION_METADATA", "").strip()
try:
    parsed = json.loads(raw)
except json.JSONDecodeError:
    parsed = {
        "session_id": session_id,
        "session_summary": raw,
        "metadata": {"source": "session-end"},
    }
else:
    if isinstance(parsed, dict):
        if "session_id" not in parsed:
            parsed["session_id"] = session_id
        if "session_summary" not in parsed:
            parsed["session_summary"] = raw
        metadata = parsed.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {"source": "session-end"}
        parsed["metadata"] = metadata
    else:
        parsed = {
            "session_id": session_id,
            "session_summary": raw,
            "metadata": {"source": "session-end"},
        }

if metadata_raw and isinstance(parsed, dict):
    try:
        extra = json.loads(metadata_raw)
    except json.JSONDecodeError:
        extra = {"source": metadata_raw}
    if isinstance(extra, dict):
        parsed.setdefault("metadata", {}).update(extra)

print(json.dumps(parsed))'
)"

curl -fsS \
  -H "Content-Type: application/json" \
  -X POST \
  --data "$payload" \
  "$GUARDIAN_URL/events/session-checkpoint" >/dev/null 2>&1 &
disown
