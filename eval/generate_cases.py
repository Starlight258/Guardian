#!/usr/bin/env python3
"""
Guardian 평가 케이스 자동 생성

Obsidian 노트를 읽어서 Claude Haiku로 다양한 쿼리를 생성해요.
  positive cases: 각 노트에서 관련 질문 N개
  negative cases: 일상적인 무관한 질문 M개

사용법:
  uv run python eval/generate_cases.py
  uv run python eval/generate_cases.py --positive-per-source 4 --negative 10
  uv run python eval/generate_cases.py --out eval/generated_cases.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

GENERATE_MODEL = "claude-haiku-4-5-20251001"
MAX_CONTENT_CHARS = 3000


def _call_llm(client, prompt: str) -> list[str]:
    response = client.messages.create(
        model=GENERATE_MODEL,
        max_tokens=1024,
        tools=[{
            "name": "output_queries",
            "description": "Return the generated queries",
            "input_schema": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Generated query strings",
                    }
                },
                "required": ["queries"],
            },
        }],
        tool_choice={"type": "tool", "name": "output_queries"},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].input["queries"]


def generate_positive_cases(client, source_name: str, content: str, n: int) -> list[dict]:
    prompt = (
        f"다음 노트를 읽고, 이 노트가 실제로 도움이 될 만한 질문 {n}개를 만들어주세요.\n"
        "AI 코딩 세션 중에 사용자가 자연스럽게 입력할 법한 다양한 질문이어야 해요.\n"
        "비슷한 질문을 반복하지 말고, 노트의 서로 다른 측면을 커버해요.\n\n"
        f"노트 ({source_name}):\n{content[:MAX_CONTENT_CHARS]}"
    )
    queries = _call_llm(client, prompt)
    return [
        {"query": q, "should_trigger": True, "expected_source": source_name}
        for q in queries[:n]
    ]


def generate_negative_cases(client, n: int) -> list[dict]:
    prompt = (
        f"AI 코딩 어시스턴트를 쓰는 중에 사용자가 입력할 수 있는 일상적인 질문 {n}개를 만들어요.\n"
        "소프트웨어 개발, AI, 코딩과 전혀 관련없어야 해요.\n"
        "날씨, 음식, 교통, 쇼핑, 운동, 일상 잡담 등 다양하게 섞어요.\n"
        "한국어로 자연스럽게 작성해요."
    )
    queries = _call_llm(client, prompt)
    return [
        {"query": q, "should_trigger": False, "expected_source": None}
        for q in queries[:n]
    ]


def load_note_sources(session) -> list[tuple[str, str]]:
    """Return (filename, combined_chunk_text) for each Obsidian note."""
    from sqlalchemy import select

    from src.models import Chunk, Source

    sources = session.execute(
        select(Source).where(Source.source_type == "note")
    ).scalars().all()

    result = []
    for source in sources:
        if not source.path:
            continue
        fname = Path(source.path).name
        chunks = session.execute(
            select(Chunk)
            .where(Chunk.source_id == source.id)
            .order_by(Chunk.chunk_index)
        ).scalars().all()
        content = "\n".join(c.text for c in chunks)
        if content.strip():
            result.append((fname, content))

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Guardian eval case generator")
    parser.add_argument("--out", default="eval/generated_cases.jsonl", type=Path)
    parser.add_argument("--positive-per-source", type=int, default=3,
                        help="노트 하나당 생성할 positive 케이스 수")
    parser.add_argument("--negative", type=int, default=8,
                        help="생성할 negative 케이스 총 수")
    args = parser.parse_args()

    import anthropic

    from src.db import SessionLocal

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    cases: list[dict] = []

    with SessionLocal() as session:
        sources = load_note_sources(session)

    if not sources:
        logger.error("노트 소스 없음 — Guardian DB가 비어있거나 노트가 수집되지 않았어요")
        sys.exit(1)

    logger.info("%d개 노트에서 케이스 생성 중...", len(sources))

    for i, (fname, content) in enumerate(sources, 1):
        logger.info("[%d/%d] %s", i, len(sources), fname)
        try:
            positive = generate_positive_cases(client, fname, content, args.positive_per_source)
            cases.extend(positive)
        except Exception as e:
            logger.warning("  positive 생성 실패: %s", e)

    logger.info("negative 케이스 %d개 생성 중...", args.negative)
    try:
        negative = generate_negative_cases(client, args.negative)
        cases.extend(negative)
    except Exception as e:
        logger.warning("negative 생성 실패: %s", e)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    pos = sum(1 for c in cases if c["should_trigger"])
    neg = sum(1 for c in cases if not c["should_trigger"])
    logger.info("완료: %d개 케이스 저장 → %s (positive %d, negative %d)",
                len(cases), args.out, pos, neg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
