# 공통 유틸리티: 해싱, 토큰 수 계산, Obsidian 경로 파싱.
from __future__ import annotations

import hashlib
import os
from pathlib import Path

OBSIDIAN_PATHS_ENV = "GUARDIAN_OBSIDIAN_PATHS"


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_tokens(text: str) -> int:
    return len(text.split())


def obsidian_paths_from_env() -> list[Path]:
    raw_paths = os.getenv(OBSIDIAN_PATHS_ENV)
    if not raw_paths:
        return []

    paths: list[Path] = []
    seen: set[Path] = set()
    for raw_path in raw_paths.split(os.pathsep):
        if not raw_path.strip():
            continue
        path = Path(raw_path).expanduser().resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        paths.append(path)
    return paths
