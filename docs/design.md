# PatchGym Design

## Objective

PatchGym is a small, deterministic coding-agent evaluation harness. It generates synthetic Python
repositories with seeded bugs, runs agents against copied workspaces, and verifies the final patch
with public tests, hidden tests, API-contract checks, and patch-budget checks.

## Task Layout

Each generated task is a self-contained directory:

```text
task/
  metadata.json
  oracle.json
  issue.md
  baseline/
  repo/
  hidden_tests/
```

- `repo/` is the workspace an agent edits.
- `baseline/` is the clean generated snapshot used for patch-budget comparison.
- `hidden_tests/` is withheld from the agent path and mounted only during verification.
- `oracle.json` describes public API signatures and forbidden edit patterns.

## Verifier Stack

The verifier computes a single `solved` value from four deterministic layers:

| Layer | Purpose |
| --- | --- |
| public tests | Confirms visible task behavior still passes |
| hidden tests | Checks withheld edge cases and regressions |
| API contract | Detects signature or public symbol drift |
| patch budget | Flags overly broad file and line changes |

`patchgym verify` exits `0` only when all layers pass. Unsolved tasks exit `1` and still print a
machine-readable summary when `--json` is used.

## Agent Boundary

Agents run on copied task repositories, not on the generated source task. PatchGym currently
supports:

- `noop` for baseline failure measurement;
- `command` for local command adapters, executed as argv without an implicit shell;
- `openai-compatible` for chat-completions APIs that return JSON full-file edits.

The runner stores per-task traces and final repository snapshots under the selected run directory.

## RL Environment Boundary

`patchgym.env.PatchGymEnv` exposes the same generated task as an RL-style episode:

```text
reset(task_dir) -> observation
step(action) -> PatchGymStepResult(observation, reward, terminated, truncated, info)
```

The action space is intentionally small and text-native:

| Action | Purpose |
| --- | --- |
| `read_file` | Inspect a visible repository file |
| `write_file` | Replace one non-test, non-metadata file |
| `run_public_tests` | Execute visible tests for feedback |
| `submit_patch` | Run the full verifier and end the episode |

The default reward is sparse: `1.0` only when the submitted patch passes public tests, hidden tests,
API contract, and patch budget. `reward_mode="layered"` provides partial credit from the same
deterministic verifier layers for experiments that need denser shaping.

Hidden tests are never copied into the editable repository. The environment reports hidden-test
pass/fail only through the verifier summary, not hidden failure text, unless a caller explicitly opts
into broader feedback for local debugging.

## Prime Verifiers Adapter

`patchgym.verifiers_adapter` is optional and imports Prime Intellect `verifiers` only when that extra
is installed. It packages generated PatchGym tasks as v1 Taskset/Harness records and scores model
completions that return the JSON full-file edit schema used by the OpenAI-compatible agent.

This adapter is a compatibility layer over PatchGym's own verifier and environment logic. The core
generator, verifier, CLI, and local env API do not depend on Prime's library.

## RLM-PatchPlan

`RLM-PatchPlan` is an optional DSPy RLM + GEPA path inside the same repo. It turns generated tasks
into structured bug-localization and patch-planning examples, evaluates exact and canonicalized
predictions, and lets GEPA optimize the textual patch-planning policy from deterministic feedback.

This path is intentionally separate from the patch executor: it measures whether the model can
identify the likely file, symbol, bug family, and repair action before attempting a code edit.

## Non-Goals

- No claim that synthetic tasks replace real-world coding benchmarks.
- No hidden provider dependency in the default generator/verifier path.
- No automatic secret handling beyond keeping credentials outside committed files.
