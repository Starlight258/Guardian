#!/usr/bin/env python3
"""Rule-based session summary from a Claude Code transcript (.jsonl)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_WRITE_TOOLS = {"Bash", "Edit", "Write", "NotebookEdit"}
_QUESTION_MARKERS = {"?", "왜", "고민", "생각"}
_MAX_MSG_LEN = 300
_MAX_USER_MSGS = 20
_MAX_TOOL_CALLS = 10
_MIN_MSG_LEN = 4


def _is_question(text: str) -> bool:
    return any(marker in text for marker in _QUESTION_MARKERS)


_NOISE_PREFIXES = ("<", "[Request interrupted", "<local-command", "<task-notification", "<command-")


def _is_noise(text: str) -> bool:
    return any(text.startswith(p) for p in _NOISE_PREFIXES)


def _extract_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block.get("text", "").strip()
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return " ".join(p for p in parts if p).strip()
    return ""


def _describe_tool(name: str, inp: dict) -> str:
    if name == "Bash":
        return inp.get("description", "").strip() or inp.get("command", "")[:80].strip()
    if name in ("Edit", "Write", "NotebookEdit"):
        return inp.get("file_path", "").strip()
    return name


def extract_summary(transcript_path: str) -> str:
    path = Path(transcript_path)
    if not path.exists():
        return ""

    user_msgs: list[str] = []
    tool_events: list[str] = []

    with path.open(encoding="utf-8") as fh:
        for raw_line in fh:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            # Claude Code transcript: content is nested under "message" key
            msg = obj.get("message") or obj
            role = msg.get("role") or obj.get("type", "")
            content = msg.get("content", "")

            if role in ("user", "human"):
                text = _extract_text(content)
                if text and len(text) >= _MIN_MSG_LEN and not _is_noise(text):
                    user_msgs.append(text[:_MAX_MSG_LEN])

            elif role == "assistant":
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            name = block.get("name", "")
                            if name in _WRITE_TOOLS:
                                desc = _describe_tool(name, block.get("input", {}))
                                if desc:
                                    tool_events.append(f"{name}: {desc}")

    if not user_msgs and not tool_events:
        return ""

    questions = [m for m in user_msgs if _is_question(m)]
    requests = [m for m in user_msgs if not _is_question(m)]

    parts: list[str] = []
    if questions:
        parts.append("## Questions")
        parts.extend(f"- {m}" for m in questions[-_MAX_USER_MSGS:])
    if requests:
        parts.append("## Requests")
        parts.extend(f"- {m}" for m in requests[-_MAX_USER_MSGS:])
    if tool_events:
        parts.append("## Actions")
        parts.extend(f"- {t}" for t in tool_events[-_MAX_TOOL_CALLS:])

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
    transcript_path = hook_data.get("transcript_path", "")
    cwd = hook_data.get("cwd", "")

    if not session_id or not transcript_path:
        sys.exit(0)

    summary = extract_summary(transcript_path)
    if not summary:
        sys.exit(0)

    payload = {
        "session_id": session_id,
        "session_summary": summary,
        "metadata": {"cwd": cwd, "source": "session-end"},
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
