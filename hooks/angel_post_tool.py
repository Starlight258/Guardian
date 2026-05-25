#!/usr/bin/env python3
"""PostToolUse hook: update Angel's mood from tool results.

Reads hook payload from stdin, updates ~/.guardian/angel-state.json.
Error detection: Bash stderr/exit-code failures → mood shifts to tired.
Test success: "passed" in output → mood shifts to happy.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_STATE_PATH = Path.home() / ".guardian" / "angel-state.json"

_ERROR_SIGNALS = ("Error:", "error:", "FAILED", "Traceback", "Exception", "failed")
_PASS_SIGNALS = (" passed", "ok", "SUCCESS", "✓", "All tests")


def _read_state() -> dict:
    try:
        return json.loads(_STATE_PATH.read_text())
    except Exception:
        return {
            "name": "Angel",
            "mood": "focused",
            "message": "",
            "message_ts": 0,
            "message_ttl": 60,
            "session_errors": 0,
            "muted": False,
        }


def _write_state(state: dict) -> None:
    try:
        _STATE_PATH.parent.mkdir(exist_ok=True)
        _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False))
    except Exception:
        pass


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        return
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    tool_name = data.get("tool_name", "")
    response = data.get("tool_response", {})
    output = str(response.get("output", ""))

    state = _read_state()
    errors = int(state.get("session_errors", 0))

    if tool_name == "Bash":
        is_error = any(sig in output for sig in _ERROR_SIGNALS)
        is_pass = any(sig in output for sig in _PASS_SIGNALS)
        if is_error and not is_pass:
            errors += 1
            state["session_errors"] = errors
            state["mood"] = "tired" if errors >= 3 else "focused"
        elif is_pass:
            state["mood"] = "happy"
            state["session_errors"] = max(0, errors - 1)

    elif tool_name in ("Edit", "Write"):
        is_error = any(sig in output for sig in _ERROR_SIGNALS)
        if is_error:
            errors += 1
            state["session_errors"] = errors
            state["mood"] = "tired" if errors >= 3 else "focused"
        else:
            state["mood"] = "happy"
            state["session_errors"] = max(0, errors - 1)

    else:
        return

    _write_state(state)


if __name__ == "__main__":
    main()
