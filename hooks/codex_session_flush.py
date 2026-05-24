#!/usr/bin/env python3
"""Codex SessionStart 훅: 이전 세션의 pending temp 파일을 Guardian에 전송한다."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PENDING_DIR = Path(tempfile.gettempdir())
PENDING_PREFIX = "guardian_codex_pending_"
PENDING_SUFFIX = ".md"
STATE_SUFFIX = ".state.json"
GUARDIAN_SCRIPT = Path(__file__).parent / "post_session_to_guardian.sh"


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        sys.exit(0)

    try:
        hook_data = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(0)

    current_session_id = hook_data.get("session_id", "")
    pending_files = list(PENDING_DIR.glob(f"{PENDING_PREFIX}*{PENDING_SUFFIX}"))

    for pending_file in pending_files:
        # 현재 세션 파일은 건너뜀 (아직 진행 중)
        current_file = f"{PENDING_PREFIX}{current_session_id}{PENDING_SUFFIX}"
        if current_session_id and pending_file.name == current_file:
            continue

        try:
            payload = pending_file.read_text(encoding="utf-8")
            if not payload.strip():
                pending_file.unlink(missing_ok=True)
                state_file = pending_file.with_name(
                    pending_file.name.replace(PENDING_SUFFIX, STATE_SUFFIX)
                )
                state_file.unlink(missing_ok=True)
                continue

            session_id = pending_file.name.removeprefix(PENDING_PREFIX).removesuffix(PENDING_SUFFIX)
            summary = payload
            if summary.startswith("# Session checkpoint"):
                summary = summary
            subprocess.run(
                ["sh", str(GUARDIAN_SCRIPT)],
                input=json.dumps(
                    {
                        "session_id": f"codex-{session_id}",
                        "session_summary": summary,
                        "metadata": {"source": "codex-session-end"},
                    }
                ),
                text=True,
                check=False,
            )
            pending_file.unlink()
            pending_file.with_name(
                pending_file.name.replace(PENDING_SUFFIX, STATE_SUFFIX)
            ).unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
