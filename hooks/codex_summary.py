#!/usr/bin/env python3
"""Codex Stop 훅: history.jsonl에서 현재 세션 프롬프트를 읽어 Guardian checkpoint 형식으로 출력한다."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HISTORY_PATH = Path.home() / ".codex" / "history.jsonl"
MAX_MESSAGES = 10


def read_session_messages(session_id: str) -> list[str]:
    if not HISTORY_PATH.exists():
        return []
    messages = []
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
                text = entry.get("text", "").strip()
                if text:
                    messages.append(text)
    return messages


def build_summary(messages: list[str]) -> str:
    parts = ["## Prompts"]
    parts.extend(f"- {m[:300]}" for m in messages[-MAX_MESSAGES:])
    return "\n".join(parts)


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit(0)

    try:
        hook_data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = hook_data.get("session_id", "")
    turn_id = hook_data.get("turn_id", "")
    cwd = hook_data.get("cwd", "")

    if not session_id:
        sys.exit(0)

    messages = read_session_messages(session_id)
    if not messages:
        sys.exit(0)

    summary = build_summary(messages)
    # turn_id를 포함해 매 턴마다 별도 entry 생성 — Guardian dedup 활용
    guardian_session_id = f"codex-{session_id}-{turn_id}" if turn_id else f"codex-{session_id}"
    payload = {
        "session_id": guardian_session_id,
        "session_summary": summary,
        "metadata": {"cwd": cwd, "source": "codex-stop"},
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
