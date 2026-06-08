from __future__ import annotations

from pathlib import Path

from patchgym.generators.cli_template import (
    generate_cli_boundary_task,
    generate_cli_contract_task,
)
from patchgym.generators.parser_template import (
    generate_parser_boundary_task,
    generate_parser_contract_task,
    generate_parser_regression_trap_task,
)
from patchgym.generators.sqlite_template import (
    generate_sqlite_boundary_task,
    generate_sqlite_integration_task,
    generate_sqlite_regression_trap_task,
)

GENERATORS = {
    ("parser", "boundary"): generate_parser_boundary_task,
    ("parser", "regression_trap"): generate_parser_regression_trap_task,
    ("parser", "contract"): generate_parser_contract_task,
    ("cli", "boundary"): generate_cli_boundary_task,
    ("cli", "contract"): generate_cli_contract_task,
    ("sqlite", "boundary"): generate_sqlite_boundary_task,
    ("sqlite", "integration"): generate_sqlite_integration_task,
    ("sqlite", "regression_trap"): generate_sqlite_regression_trap_task,
}


def generate_tasks(
    out_dir: str | Path,
    templates: list[str],
    n: int,
    seed: int,
    bug_family: str = "boundary",
) -> None:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    for template in templates:
        generator = GENERATORS.get((template, bug_family))
        if generator is None:
            raise ValueError(f"Unsupported task family for MVP: {template}.{bug_family}")

        for offset in range(n):
            task_seed = seed + offset
            task_id = f"{template}.{bug_family}.{task_seed:04d}"
            task_dir = root / task_id
            generator(task_dir, seed=task_seed)
