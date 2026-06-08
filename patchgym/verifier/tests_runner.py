from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from pathlib import Path


def run_pytest(target: Path, *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        str(target),
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    merged_env = os.environ.copy()
    merged_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        merged_env.update(env)

    # Verification intentionally invokes pytest against generated local task repositories.
    completed = subprocess.run(  # nosec B603
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        env=merged_env,
    )

    return {
        "passed": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
