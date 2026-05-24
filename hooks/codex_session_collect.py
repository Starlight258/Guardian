#!/usr/bin/env python3
"""Codex Stop 훅: 새 프롬프트만 pending 파일에 append한다.
실제 Guardian 전송은 codex_session_flush.py(SessionStart 훅)에서 수행한다."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HISTORY_PATH = Path.home() / ".codex" / "history.jsonl"
PENDING_DIR = Path(tempfile.gettempdir())
PENDING_PREFIX = "guardian_codex_pending_"
PENDING_SUFFIX = ".md"
STATE_SUFFIX = ".state.json"
MAX_MESSAGES = 20
MIN_MSG_LEN = 4


def read_session_entries(session_id: str) -> list[dict[str, object]]:
    if not HISTORY_PATH.exists():
        return []
    messages: list[dict[str, object]] = []
    with HISTORY_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("session_id") == session_id:
                text = str(entry.get("text", "")).strip()
                ts = entry.get("ts", 0)
                if text and len(text) >= MIN_MSG_LEN:
                    messages.append({"ts": ts, "text": text})
    return messages


def load_last_ts(state_path: Path) -> int:
    if not state_path.exists():
        return 0
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    last_ts = data.get("last_ts", 0)
    return int(last_ts) if isinstance(last_ts, int) or str(last_ts).isdigit() else 0


def write_state(state_path: Path, *, last_ts: int) -> None:
    state_path.write_text(json.dumps({"last_ts": last_ts}), encoding="utf-8")


def ensure_pending_file(pending_file: Path, *, session_id: str, cwd: str) -> None:
    if pending_file.exists():
        return
    pending_file.write_text(
        "\n".join(
            [
                "# Session checkpoint",
                "",
                f"Session: codex-{session_id}",
                f"CWD: {cwd or 'unknown'}",
                "",
                "## Prompts",
                "",
            ]
        ),
        encoding="utf-8",
    )


def append_prompt_block(pending_file: Path, *, messages: list[str], latest_ts: int) -> None:
    block = ["## Stop", ""]
    block.extend(f"- {message[:300]}" for message in messages[-MAX_MESSAGES:])
    block.extend(["", f"Last prompt ts: {latest_ts}", ""])
    with pending_file.open("a", encoding="utf-8") as f:
        f.write("\n".join(block))


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit(0)

    try:
        hook_data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = hook_data.get("session_id", "")
    cwd = hook_data.get("cwd", "")

    if not session_id:
        sys.exit(0)

    state_file = PENDING_DIR / f"{PENDING_PREFIX}{session_id}{STATE_SUFFIX}"
    pending_file = PENDING_DIR / f"{PENDING_PREFIX}{session_id}{PENDING_SUFFIX}"
    last_ts = load_last_ts(state_file)

    entries = read_session_entries(session_id)
    messages = [
        str(entry["text"])
        for entry in entries
        if isinstance(entry.get("ts"), int) and int(entry["ts"]) > last_ts
    ]
    latest_ts = max(
        [
            int(entry["ts"])
            for entry in entries
            if isinstance(entry.get("ts"), int) and int(entry["ts"]) > last_ts
        ],
        default=last_ts,
    )

    if not messages:
        sys.exit(0)

    ensure_pending_file(pending_file, session_id=session_id, cwd=cwd)
    append_prompt_block(pending_file, messages=messages, latest_ts=latest_ts)
    write_state(state_file, last_ts=latest_ts)


if __name__ == "__main__":
    main()
