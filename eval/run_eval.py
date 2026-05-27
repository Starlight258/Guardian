#!/usr/bin/env python3
"""
Guardian RAGAS 평가 루프

context_precision  : expected_source가 상위 검색 결과에 포함된 비율
false_positive_rate: should_trigger=False인데 angel이 발동된 비율

기준 (README):
  context_precision  >= 0.6
  false_positive_rate <= 0.30

사용법:
  uv run python eval/run_eval.py
  uv run python eval/run_eval.py --dataset eval/cases.jsonl --out eval/results
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

CONTEXT_PRECISION_MIN = 0.6
FALSE_POSITIVE_MAX = 0.30


@dataclass
class EvalCase:
    query: str
    should_trigger: bool
    expected_source: str | None = None
    note: str | None = None


@dataclass
class CaseResult:
    case: EvalCase
    triggered: bool
    retrieved_sources: list[str]
    retrieved_texts: list[str]
    angel_message: str | None
    relevance_score: float | None
    drop_reason: str | None


def load_cases(path: Path) -> list[EvalCase]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = json.loads(line)
        cases.append(EvalCase(**{k: v for k, v in d.items() if k in EvalCase.__dataclass_fields__}))
    return cases


def run_cases(cases: list[EvalCase]) -> list[CaseResult]:
    from src.db import SessionLocal
    from src.llm import make_llm_client
    from src.models import Chunk
    from src.service.graph import GraphService
    from src.service.recall import RecallAgent

    logger.info("GraphService 초기화 중...")
    graph_service = GraphService()
    with SessionLocal() as session:
        graph_service.reconstruct(session)

    agent = RecallAgent(
        graph_service=graph_service,
        llm_client=make_llm_client(),
        persist_angel_message=False,
    )

    results: list[CaseResult] = []
    for i, case in enumerate(cases, 1):
        logger.info("[%d/%d] %s", i, len(cases), case.query)
        with SessionLocal() as session:
            result = agent.recall(session, prompt=case.query)
            retrieved_texts: list[str] = []
            retrieved_sources: list[str] = []
            for chunk_id in result.retrieved_chunk_ids:
                chunk = session.get(Chunk, chunk_id)
                if chunk:
                    retrieved_texts.append(chunk.text)
                    if chunk.source and chunk.source.path:
                        retrieved_sources.append(Path(chunk.source.path).name)

        results.append(CaseResult(
            case=case,
            triggered=result.angel_triggered,
            retrieved_sources=retrieved_sources,
            retrieved_texts=retrieved_texts,
            angel_message=result.angel_message,
            relevance_score=result.relevance_score,
            drop_reason=result.drop_reason,
        ))
    return results


def _context_precision(results: list[CaseResult]) -> float:
    """expected_source가 주어진 케이스에서 상위 검색 결과에 포함된 비율."""
    labeled = [r for r in results if r.case.expected_source]
    if not labeled:
        return 1.0
    hits = sum(1 for r in labeled if r.case.expected_source in r.retrieved_sources)
    return hits / len(labeled)


def compute_summary(results: list[CaseResult]) -> dict:
    positive_cases = [r for r in results if r.case.should_trigger]
    negative_cases = [r for r in results if not r.case.should_trigger]

    false_positives = sum(1 for r in negative_cases if r.triggered)
    false_negatives = sum(1 for r in positive_cases if not r.triggered)

    fp_rate = false_positives / len(negative_cases) if negative_cases else 0.0
    fn_rate = false_negatives / len(positive_cases) if positive_cases else 0.0
    cp = _context_precision(results)
    passed = cp >= CONTEXT_PRECISION_MIN and fp_rate <= FALSE_POSITIVE_MAX

    return {
        "timestamp": datetime.now().isoformat(),
        "total_cases": len(results),
        "metrics": {
            "context_precision": round(cp, 3),
            "false_positive_rate": round(fp_rate, 3),
            "false_negative_rate": round(fn_rate, 3),
        },
        "thresholds": {
            "context_precision_min": CONTEXT_PRECISION_MIN,
            "false_positive_max": FALSE_POSITIVE_MAX,
        },
        "pass": passed,
        "cases": [
            {
                "query": r.case.query,
                "should_trigger": r.case.should_trigger,
                "triggered": r.triggered,
                "expected_source": r.case.expected_source,
                "retrieved_sources": r.retrieved_sources[:3],
                "angel_message": r.angel_message,
                "relevance_score": r.relevance_score,
                "drop_reason": r.drop_reason,
            }
            for r in results
        ],
    }


def print_summary(summary: dict, out_path: Path) -> None:
    m = summary["metrics"]
    t = summary["thresholds"]
    passed = summary["pass"]

    cp_ok = m["context_precision"] >= t["context_precision_min"]
    fp_ok = m["false_positive_rate"] <= t["false_positive_max"]

    print()
    print("=" * 52)
    print("  Guardian RAGAS Evaluation")
    print("=" * 52)
    print(f"  context_precision   {m['context_precision']:.3f}  "
          f"(≥ {t['context_precision_min']})  {'✓' if cp_ok else '✗'}")
    print(f"  false_positive_rate {m['false_positive_rate']:.3f}  "
          f"(≤ {t['false_positive_max']})  {'✓' if fp_ok else '✗'}")
    print(f"  false_negative_rate {m['false_negative_rate']:.3f}")
    print("-" * 52)
    print(f"  {'PASS ✓' if passed else 'FAIL ✗'}  ({summary['total_cases']} cases)")
    print(f"  saved → {out_path}")
    print("=" * 52)
    print()

    for case in summary["cases"]:
        trigger_ok = case["triggered"] == case["should_trigger"]
        mark = "✓" if trigger_ok else "✗"
        print(f"  {mark} [{('T' if case['triggered'] else '_')}] {case['query'][:50]}")
        if case["angel_message"]:
            print(f"      → {case['angel_message'][:80]}")
        elif case["drop_reason"]:
            print(f"      → dropped: {case['drop_reason']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Guardian RAGAS evaluation loop")
    parser.add_argument("--dataset", default="eval/cases.jsonl", type=Path,
                        help="JSONL 평가 데이터셋 경로")
    parser.add_argument("--out", default="eval/results", type=Path,
                        help="결과 저장 디렉터리")
    args = parser.parse_args()

    if not args.dataset.exists():
        logger.error("데이터셋 파일 없음: %s", args.dataset)
        sys.exit(1)

    cases = load_cases(args.dataset)
    logger.info("%d개 케이스 로드됨", len(cases))

    results = run_cases(cases)
    summary = compute_summary(results)

    args.out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_path = args.out / f"{ts}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print_summary(summary, out_path)
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
