# PatchGym

PatchGym is a lightweight coding-agent evaluation repo. It generates small multi-file Python repositories with seeded bugs, runs an agent against a copied workspace, and grades the final patch with deterministic public tests, hidden tests, API-contract checks, and patch-budget checks.

The project also includes `RLM-PatchPlan`, an optional DSPy RLM + GEPA harness that optimizes a bug-localization and patch-planning prompt over the generated tasks.

PatchGym can also be used as a dependency-free RL-style coding environment: an episode exposes
visible repository state, accepts file/action steps, and returns verifier-grounded terminal rewards.
An optional Prime Intellect `verifiers` adapter is provided for v1 Taskset/Harness workflows.

See [docs/design.md](docs/design.md) for the repository architecture and verifier stack.

## Why This Exists

Most small coding-agent demos only report whether visible tests pass. PatchGym is designed to expose more diagnostic failure modes:

- passing public tests while failing hidden tests;
- breaking a public API contract while fixing local behavior;
- touching too many files for a tiny bug;
- confusing bug-family labels even when the root cause is found;
- prompt optimization improving a dev split but needing held-out verification.

## Features

- Deterministic task generation from seeds.
- Parser, CLI, and SQLite mini-repository templates.
- Boundary, contract, integration, and regression-trap bug families.
- Public tests available to the agent, hidden tests held back for verification.
- AST-based API-contract checks.
- Patch-budget checks against the generated baseline.
- Black-box agent runner with trace logs and final repo snapshots.
- RL-style `reset`/`step` environment API with read/write/test/submit actions.
- Sparse or layered verifier rewards.
- Optional Prime Intellect `verifiers` taskset adapter.
- OpenAI-compatible chat-completions adapter.
- Optional DSPy RLM/GEPA optimizer for structured patch-plan prediction.
- Markdown and JSON summaries.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,agent,dspy]'
```

For the core generator/verifier/env path, `pip install -e '.[dev]'` is enough. The OpenAI-compatible agent path uses the `agent` extra. The RLM/GEPA optimizer uses the `dspy` extra. The Prime Intellect adapter uses the `verifiers` extra.

## Generate Tasks

```bash
python3 -m patchgym generate \
  --out generated_tasks/demo \
  --templates parser,cli,sqlite \
  --n 1 \
  --seed 42
```

Generate harder families:

```bash
python3 -m patchgym generate \
  --out generated_tasks/hard \
  --templates sqlite \
  --bug-family regression_trap \
  --n 5 \
  --seed 42
```

Supported families:

| Template | Families |
| --- | --- |
| `parser` | `boundary`, `contract`, `regression_trap` |
| `cli` | `boundary`, `contract` |
| `sqlite` | `boundary`, `integration`, `regression_trap` |

## Verify A Task

Starter repos are intentionally buggy. Public tests may pass while hidden tests fail.

```bash
python3 -m patchgym verify \
  --task generated_tasks/demo/parser.boundary.0042 \
  --json
```

Verify a patched or copied repo:

```bash
python3 -m patchgym verify \
  --task generated_tasks/demo/parser.boundary.0042 \
  --repo runs/my-agent/parser.boundary.0042/final_repo \
  --json
```

A task is solved only when all verifier layers pass:

- public tests;
- hidden tests;
- API contract;
- patch budget.

The `verify` command exits `0` only when the task is solved. It exits `1` for unsolved task
repositories while still printing the JSON or text summary.

## Run An Agent

### No-op Baseline

```bash
python3 -m patchgym run-suite \
  --tasks generated_tasks/demo \
  --agent noop \
  --out runs/noop-demo
```

### Local-command Agent

PatchGym can run any local command against the copied repo. The command receives:

- `PATCHGYM_TASK_DIR`
- `PATCHGYM_REPO_DIR`
- `PATCHGYM_TRACE_PATH`

```bash
python3 -m patchgym run \
  --task generated_tasks/demo/parser.boundary.0042 \
  --agent command \
  --agent-command "python3 my_agent.py" \
  --out runs/command-demo
```

The command is parsed into argv form and executed without a shell. For shell-specific behavior,
invoke a shell explicitly, for example `--agent-command "bash -lc 'python3 my_agent.py'"`.

### OpenAI-compatible API Agent

Set credentials for any OpenAI-compatible chat-completions endpoint:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="<your-openai-compatible-base-url>"  # optional for OpenAI
```

Run one task:

```bash
python3 -m patchgym run \
  --task generated_tasks/demo/parser.boundary.0042 \
  --agent openai-compatible \
  --model gpt-4o-mini \
  --out runs/openai-demo
```

The adapter asks the model to return JSON full-file edits. PatchGym rejects edits to tests and generated metadata before verification.

## RL Environment API

Use `PatchGymEnv` directly when you want an episode interface instead of a one-shot agent run:

```python
from patchgym.env import PatchGymEnv, PatchGymEnvConfig

env = PatchGymEnv(config=PatchGymEnvConfig(work_dir="runs/env-demo"))
obs = env.reset("generated_tasks/demo/parser.boundary.0042")

source = obs["repo_files"]["src/miniparse/date_parser.py"]
env.step({
    "type": "write_file",
    "path": "src/miniparse/date_parser.py",
    "content": source.replace(
        "if value is None:",
        "if value is None or value.strip() == \"\":",
    ),
})
result = env.step({"type": "submit_patch"})
assert result.reward == 1.0
```

Supported actions:

| Action | Fields | Notes |
| --- | --- | --- |
| `read_file` | `path` | Reads a repository file into the observation. |
| `write_file` | `path`, `content` | Full-file replacement. Test and metadata edits are rejected. |
| `run_public_tests` | none | Runs visible tests only. |
| `submit_patch` | none | Runs the full verifier and terminates the episode. |

By default, `submit_patch` returns a sparse reward: `1.0` if all verifier layers pass and `0.0`
otherwise. Set `PatchGymEnvConfig(reward_mode="layered")` to assign partial credit for public
tests, hidden tests, API contract, and patch budget.

Replay an action script:

```bash
python3 -m patchgym episode \
  --task generated_tasks/demo/parser.boundary.0042 \
  --actions actions.jsonl \
  --out runs/env-demo \
  --json
```

Each line in `actions.jsonl` is a JSON action object.

## Prime Intellect Verifiers Adapter

Install the optional adapter dependency:

```bash
pip install -e '.[verifiers]'
```

The adapter module is `patchgym.verifiers_adapter`. It exposes:

- `load_taskset(config)`;
- `load_environment(config)`;
- `PatchGymTasksetConfig`;
- pure helpers such as `score_patchgym_completion`.

The adapter follows Prime's v1 Taskset/Harness shape and scores a model response that returns the
same JSON edit schema used by the OpenAI-compatible agent:

```json
{"edits": [{"path": "src/module.py", "content": "full replacement file"}]}
```

## RLM-PatchPlan

Generate a structured patch-plan dataset:

```bash
python3 -m rlm_patchplan.generate \
  --out data/tasks_patchplan_80.jsonl \
  --n 80 \
  --seed 67
```

Evaluate the unoptimized RLM planner:

```bash
python3 -m rlm_patchplan.evaluate \
  --program rlm \
  --provider openai-compatible \
  --model openai/gpt-4o-mini \
  --data data/tasks_patchplan_80.jsonl \
  --split test \
  --out runs/rlm_test.json \
  --json
```

Optimize the RLM prompt with GEPA:

```bash
python3 -m rlm_patchplan.optimize_gepa \
  --data data/tasks_patchplan_80.jsonl \
  --provider openai-compatible \
  --model openai/gpt-4o-mini \
  --reflection-provider openai-compatible \
  --reflection-model openai/gpt-4o-mini \
  --artifact artifacts/optimized_patchplanner.json \
  --log-dir runs/gepa_patchplan \
  --max-metric-calls 40
```

Evaluate an optimized artifact:

```bash
python3 -m rlm_patchplan.evaluate \
  --program optimized \
  --provider openai-compatible \
  --model openai/gpt-4o-mini \
  --artifact artifacts/optimized_patchplanner.json \
  --data data/tasks_patchplan_80.jsonl \
  --split test \
  --out runs/optimized_test.json \
  --json
```

Build a Markdown comparison report:

```bash
python3 -m rlm_patchplan.report \
  --runs runs/rlm_test.json runs/optimized_test.json \
  --out reports/patchplan_report.md
```

## Development

```bash
pip install -e '.[dev,agent,dspy]'
python3 -m pytest -q
python3 -m compileall -q patchgym rlm_patchplan tests
```

The test suite covers deterministic generation, verifier behavior, runner behavior, OpenAI-compatible adapter parsing, RLM-PatchPlan scoring, and the harder task families.

## Repository Hygiene

Generated artifacts are ignored by git:

- `generated_tasks*/`
- `runs/`
- `reports/`
- `artifacts/`
- `data/`
- `.env`

Keep committed examples small and deterministic. Do not commit provider keys, custom endpoint values, generated run logs, or large task dumps.

## Current Limitations

- Task repositories are synthetic and small.
- The OpenAI-compatible agent currently uses full-file JSON replacements, not a richer tool protocol.
- The verifier is deterministic but template-aware.
- RLM-PatchPlan reports exact and canonicalized metrics, but results should still be interpreted by bug family and held-out split.

## Related Project

RLM-GEPA Retrieval is a sibling project that applies the same DSPy RLM + GEPA optimization pattern
to retrieval-policy evaluation over a local corpus rather than coding-agent patch repair. It is
intended to live as a separate repository.
