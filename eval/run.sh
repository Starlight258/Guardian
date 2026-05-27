#!/usr/bin/env bash
# Guardian evaluation — installs eval deps and runs all metrics
set -e
cd "$(dirname "$0")/.."
uv sync --group eval --quiet
uv run python eval/run_eval.py "$@"
