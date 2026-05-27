#!/usr/bin/env bash
# Guardian evaluation
#
# Usage:
#   bash eval/run.sh                  # 큐레이션 케이스로 평가 (ragas 포함)
#   bash eval/run.sh --generate       # 케이스 자동 생성 후 평가
#   bash eval/run.sh --skip-ragas     # ragas 생략 (빠른 평가)
#   bash eval/run.sh --generate --skip-ragas
set -e
cd "$(dirname "$0")/.."
uv sync --group eval --quiet

GENERATE=0
EVAL_ARGS=()
for arg in "$@"; do
    if [ "$arg" = "--generate" ]; then
        GENERATE=1
    else
        EVAL_ARGS+=("$arg")
    fi
done

if [ "$GENERATE" -eq 1 ]; then
    echo "케이스 자동 생성 중..."
    uv run python eval/generate_cases.py
    uv run python eval/run_eval.py --dataset eval/generated_cases.jsonl "${EVAL_ARGS[@]}"
else
    uv run python eval/run_eval.py "${EVAL_ARGS[@]}"
fi
