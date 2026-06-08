#!/usr/bin/env bash
set -euo pipefail

MODEL="${MODEL:-gpt-4o-mini}"
TASKS_ROOT="${TASKS_ROOT:-generated_tasks/openai-compatible-smoke}"
RUN_ROOT="${RUN_ROOT:-runs/openai-compatible-e2e}"
REPORT_PATH="${REPORT_PATH:-reports/openai-compatible-e2e.md}"

: "${OPENAI_API_KEY:?Set OPENAI_API_KEY before running the OpenAI-compatible smoke.}"

python3 -m patchgym generate \
  --out "$TASKS_ROOT" \
  --templates parser \
  --n 1 \
  --seed 42

python3 -m patchgym run \
  --task "$TASKS_ROOT/parser.boundary.0042" \
  --agent openai-compatible \
  --model "$MODEL" \
  --max-tokens 4096 \
  --out "$RUN_ROOT"

python3 -m patchgym summarize "$RUN_ROOT" --out "$REPORT_PATH"

python3 -m patchgym verify \
  --task "$TASKS_ROOT/parser.boundary.0042" \
  --repo "$RUN_ROOT/parser.boundary.0042/final_repo" \
  --json

printf 'Report: %s\n' "$REPORT_PATH"
printf 'Run summary: %s\n' "$RUN_ROOT/parser.boundary.0042/summary.json"
