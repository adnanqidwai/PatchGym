from __future__ import annotations

import argparse
import json
from pathlib import Path

from rlm_patchplan.schema import PatchPlanTask
from rlm_patchplan.templates import TASK_BUILDERS


def split_for_index(index: int, n: int) -> str:
    if n < 4:
        raise ValueError("n must be at least 4 to create train, dev, and test splits")

    if n >= 80:
        if index < 40:
            return "train"
        if index < 60:
            return "dev"
        return "test"

    train_end = max(1, n // 2)
    dev_end = max(train_end + 1, (3 * n) // 4)
    dev_end = min(dev_end, n - 1)

    if index < train_end:
        return "train"
    if index < dev_end:
        return "dev"
    return "test"


def generate_tasks(n: int, seed: int) -> list[PatchPlanTask]:
    if n < 4:
        raise ValueError("n must be at least 4 to create train, dev, and test splits")

    tasks: list[PatchPlanTask] = []
    for offset in range(n):
        builder = TASK_BUILDERS[offset % len(TASK_BUILDERS)]
        task_seed = seed + offset
        tasks.append(builder(task_seed, split_for_index(offset, n)))
    return tasks


def write_tasks_jsonl(tasks: list[PatchPlanTask], out_file: str | Path) -> None:
    path = Path(out_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for task in tasks:
            handle.write(json.dumps(task.to_record(), sort_keys=True) + "\n")


def generate_tasks_jsonl(out_file: str | Path, *, n: int, seed: int) -> list[PatchPlanTask]:
    tasks = generate_tasks(n=n, seed=seed)
    write_tasks_jsonl(tasks, out_file)
    return tasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rlm_patchplan.generate")
    parser.add_argument("--n", type=int, required=True, help="Number of JSONL tasks to generate; must be >= 4")
    parser.add_argument("--out", required=True, help="Output JSONL path")
    parser.add_argument("--seed", type=int, default=7, help="First task seed/id suffix")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    tasks = generate_tasks_jsonl(args.out, n=args.n, seed=args.seed)
    print(f"wrote {len(tasks)} tasks to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
