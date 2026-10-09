#!/usr/bin/env python3
"""Validate an AAR method's import-time and training-entrypoint contract."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aar.phase_timing import REQUIRED_METHOD_PHASES  # noqa: E402


def _required_phases(tree: ast.AST) -> set[str]:
    observed: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        for item in node.items:
            call = item.context_expr
            if not isinstance(call, ast.Call) or not call.args:
                continue
            function = call.func
            name = (
                function.id
                if isinstance(function, ast.Name)
                else function.attr if isinstance(function, ast.Attribute) else ""
            )
            value = call.args[0]
            if (
                name == "phase"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                observed.add(value.value)
    return observed


def validate(
    method_path: Path,
    *,
    run_dry_run: bool = False,
    require_gemma4_targets: bool = False,
) -> dict[str, Any]:
    method_path = method_path.resolve()
    source = method_path.read_bytes()
    source_text = source.decode("utf-8", errors="replace")
    source_hash = hashlib.sha256(source).hexdigest()
    errors: list[str] = []
    try:
        tree = ast.parse(source, filename=str(method_path))
    except SyntaxError as error:
        tree = None
        errors.append(f"syntax error: {error}")

    if tree is not None:
        missing = sorted(set(REQUIRED_METHOD_PHASES) - _required_phases(tree))
        if missing:
            errors.append(f"missing required phase contexts: {', '.join(missing)}")
        if (
            "BitsAndBytesConfig" in source_text
            and importlib.util.find_spec("bitsandbytes") is None
        ):
            errors.append(
                "BitsAndBytesConfig requires bitsandbytes, which is not installed"
            )
        if require_gemma4_targets:
            normalized_source = source_text.replace("\\\\", "\\")
            required_target = (
                r"model\.language_model\.layers\.\d+\.self_attn\."
                r"(q_proj|v_proj)"
            )
            if required_target not in normalized_source:
                errors.append(
                    "Gemma-4 PEFT must use target_modules regex "
                    f"{required_target}"
                )

    module = None
    if tree is not None:
        module_name = f"aar_contract_{method_path.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, method_path)
        if spec is None or spec.loader is None:
            errors.append("could not create an import specification")
        else:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            sys.path.insert(0, str(method_path.parent))
            try:
                spec.loader.exec_module(module)
            except Exception as error:  # noqa: BLE001 - report candidate import errors
                errors.append(f"method import failed: {type(error).__name__}: {error}")
            finally:
                sys.path.pop(0)

    if module is not None:
        method_config = getattr(module, "MethodConfig", None)
        run_experiment = getattr(module, "run_experiment", None)
        if not inspect.isclass(method_config):
            errors.append("MethodConfig class is missing")
        if not callable(run_experiment):
            errors.append("run_experiment callable is missing")
        if inspect.isclass(method_config):
            try:
                config_kwargs: dict[str, Any] = {
                    "output_dir": "/tmp/aar-method-contract"
                }
                if run_dry_run:
                    config_kwargs["dry_run"] = True
                config = method_config(**config_kwargs)
            except Exception as error:  # noqa: BLE001 - report candidate contract errors
                errors.append(
                    "MethodConfig(output_dir=...) failed: "
                    f"{type(error).__name__}: {error}"
                )
            else:
                if not hasattr(config, "output_dir"):
                    errors.append("MethodConfig instance has no output_dir attribute")
                if callable(run_experiment):
                    try:
                        inspect.signature(run_experiment).bind(config)
                    except TypeError as error:
                        errors.append(f"run_experiment(config) contract failed: {error}")
                    if run_dry_run and not errors:
                        try:
                            with tempfile.TemporaryDirectory(
                                prefix="aar-method-dry-run-"
                            ) as temp_dir:
                                config.output_dir = temp_dir
                                result = run_experiment(config)
                        except Exception as error:  # noqa: BLE001
                            errors.append(
                                "run_experiment(MethodConfig(dry_run=True)) failed: "
                                f"{type(error).__name__}: {error}"
                            )
                        else:
                            if not isinstance(result, dict) or not {
                                "model_path",
                                "method",
                            }.issubset(result):
                                errors.append(
                                    "dry-run result must contain model_path and method"
                                )

    return {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "method_path": str(method_path),
        "source_sha256": source_hash,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("method_path", type=Path)
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--run-dry-run", action="store_true")
    parser.add_argument("--require-gemma4-targets", action="store_true")
    args = parser.parse_args()
    proof = args.proof or args.method_path.parent / ".aar-method-contract.json"
    try:
        source_hash = hashlib.sha256(args.method_path.read_bytes()).hexdigest()
    except OSError:
        source_hash = ""
    proof.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "running",
                "method_path": str(args.method_path.resolve()),
                "source_sha256": source_hash,
                "errors": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    try:
        result = validate(
            args.method_path,
            run_dry_run=args.run_dry_run,
            require_gemma4_targets=args.require_gemma4_targets,
        )
    except Exception as error:  # noqa: BLE001 - always leave a diagnostic proof
        result = {
            "schema_version": 1,
            "status": "failed",
            "method_path": str(args.method_path.resolve()),
            "source_sha256": "",
            "errors": [f"validator failed: {type(error).__name__}: {error}"],
        }
    proof.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
