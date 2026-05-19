#!/usr/bin/env sh
set -eu

GUARDIAN_URL="${GUARDIAN_URL:-http://127.0.0.1:8000}"

repo_root="$(git rev-parse --show-toplevel)"
commit_sha="$(git rev-parse HEAD)"
commit_message="$(git log -1 --format=%B "$commit_sha")"
branch="$(git branch --show-current || true)"
changed_files="$(git diff-tree --root -m --no-commit-id --name-only -r "$commit_sha")"
session_summary="${GUARDIAN_CHECKPOINT_SUMMARY:-$commit_message}"

payload="$(
  COMMIT_SHA="$commit_sha" \
  COMMIT_MESSAGE="$commit_message" \
  BRANCH="$branch" \
  CHANGED_FILES="$changed_files" \
  SESSION_SUMMARY="$session_summary" \
  python3 -c 'import json, os
files = [line for line in os.environ["CHANGED_FILES"].splitlines() if line.strip()]
print(json.dumps({
    "commit_sha": os.environ["COMMIT_SHA"],
    "commit_message": os.environ["COMMIT_MESSAGE"].strip(),
    "branch": os.environ["BRANCH"] or None,
    "changed_files": files,
    "session_summary": os.environ["SESSION_SUMMARY"].strip(),
}))'
)"

curl -fsS \
  -H "Content-Type: application/json" \
  -X POST \
  --data "$payload" \
  "$GUARDIAN_URL/events/checkpoint" >/dev/null
