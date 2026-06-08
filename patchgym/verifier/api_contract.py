from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


def _module_path(repo_dir: Path, module_name: str) -> Path:
    parts = module_name.split(".")
    return repo_dir / "src" / Path(*parts[:-1]) / f"{parts[-1]}.py"


def _format_annotation(node: ast.expr | None) -> str:
    if node is None:
        return "Any"
    return ast.unparse(node)


def _function_signature(func: ast.FunctionDef) -> str:
    args = func.args
    params: list[str] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults_offset = len(positional) - len(args.defaults)

    for index, arg in enumerate(positional):
        name = arg.arg
        if arg.annotation is not None:
            name = f"{name}: {_format_annotation(arg.annotation)}"
        default_index = index - defaults_offset
        if default_index >= 0:
            default = ast.unparse(args.defaults[default_index])
            name = f"{name} = {default}"
        params.append(name)

    if args.vararg is not None:
        prefix = "*" if not args.kwonlyargs else "*"
        name = f"{prefix}{args.vararg.arg}"
        if args.vararg.annotation is not None:
            name = f"{name}: {_format_annotation(args.vararg.annotation)}"
        params.append(name)
    elif args.kwonlyargs:
        params.append("*")

    for index, arg in enumerate(args.kwonlyargs):
        name = arg.arg
        if arg.annotation is not None:
            name = f"{name}: {_format_annotation(arg.annotation)}"
        if args.kw_defaults[index] is not None:
            default = ast.unparse(args.kw_defaults[index])
            name = f"{name} = {default}"
        params.append(name)

    if args.kwarg is not None:
        name = f"**{args.kwarg.arg}"
        if args.kwarg.annotation is not None:
            name = f"{name}: {_format_annotation(args.kwarg.annotation)}"
        params.append(name)

    params_text = ", ".join(params)
    returns = _format_annotation(func.returns)
    return f"({params_text}) -> {returns}"


def check_api_contract(repo_dir: Path, oracle: dict[str, Any]) -> dict[str, Any]:
    violations: list[str] = []

    for entry in oracle.get("public_api", []):
        module_name = entry["module"]
        function_name = entry["name"]
        expected_signature = entry.get("signature")
        module_path = _module_path(repo_dir, module_name)

        if not module_path.is_file():
            violations.append(f"missing module file: {module_name}")
            continue

        tree = ast.parse(module_path.read_text())
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        func = functions.get(function_name)
        if func is None:
            violations.append(f"missing function: {module_name}.{function_name}")
            continue

        actual_signature = _function_signature(func)
        if expected_signature and actual_signature != expected_signature:
            violations.append(
                f"signature mismatch for {module_name}.{function_name}: "
                f"expected {expected_signature}, got {actual_signature}"
            )

    return {"passed": not violations, "violations": violations}
