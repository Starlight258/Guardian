#!/usr/bin/env sh
set -eu

GUARDIAN_URL="${GUARDIAN_URL:-http://127.0.0.1:8000}"

commit_sha="$(git rev-parse HEAD)"
commit_message="$(git log -1 --format=%B "$commit_sha")"
changed_files="$(git diff-tree --root -m --no-commit-id --name-only -r "$commit_sha")"
entire_checkpoint="$(git log -1 --format='%(trailers:key=Entire-Checkpoint,valueonly)' "$commit_sha" | sed '/^[[:space:]]*$/d' | head -n 1)"

if [ -n "$entire_checkpoint" ]; then
  session_summary="$(entire checkpoint explain --commit HEAD --short --no-pager 2>/dev/null || true)"
else
  session_summary=""
fi

if [ -z "$(printf '%s' "$session_summary" | tr -d '[:space:]')" ]; then
  session_summary="$(
    COMMIT_MESSAGE="$commit_message" \
    CHANGED_FILES="$changed_files" \
    python3 -c 'import os
import re
message = os.environ["COMMIT_MESSAGE"].strip()
files = [line.strip() for line in os.environ["CHANGED_FILES"].splitlines() if line.strip()]
file_count = len(files)
preview = ", ".join(files[:5])
if file_count > 5:
    preview = f"{preview}, and {file_count - 5} more"
question_keywords = ("?", "왜", "고민", "생각")
questions = []
for line in message.splitlines():
    line = line.strip()
    if line and any(keyword in line for keyword in question_keywords):
        questions.append(line)
questions = list(dict.fromkeys(questions))

lines = ["Rule-based checkpoint summary."]
if message:
    lines.append(f"Commit message: {message}")
if questions:
    lines.append("Questions:")
    lines.extend(f"- {question}" for question in questions)
if file_count:
    lines.append(f"Changed files ({file_count}): {preview}")
else:
    lines.append("Changed files: none detected")
print("\n".join(lines))'
  )"
fi

branch="$(git branch --show-current || true)"

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
