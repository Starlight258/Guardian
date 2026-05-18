from __future__ import annotations

import hashlib


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_tokens(text: str) -> int:
    return len(text.split())
