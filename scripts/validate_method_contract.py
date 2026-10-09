#!/usr/bin/env python3
"""Validate an AAR method's import-time and training-entrypoint contract."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
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


def _gemma_regex_wrapped_in_collection(tree: ast.AST) -> bool:
    """PEFT treats collections as literal suffixes; only a string is a regex."""

    def is_regex_collection(node: ast.AST) -> bool:
        if not isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            return False
        return any(
            isinstance(element, ast.Constant)
            and isinstance(element.value, str)
            and ("\\" in element.value or "|" in element.value)
            for element in node.elts
        )

    bad_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and is_regex_collection(node.value):
            bad_names.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and is_regex_collection(node.value)
        ):
            bad_names.add(node.target.id)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "target_modules":
                continue
            if is_regex_collection(keyword.value) or (
                isinstance(keyword.value, ast.Name)
                and keyword.value.id in bad_names
            ):
                return True
    return False


def _unsupported_training_arguments(tree: ast.AST) -> list[str]:
    """Return explicit TrainingArguments keywords absent from this environment."""
    # Run 10 executes on the locked ARM64 Transformers 5.17 environment. Keep
    # its known removal here as a fallback so the CPU-only dev/CI validator,
    # where Transformers is intentionally absent, enforces the same contract.
    supported: set[str] | None = None
    spec = importlib.util.find_spec("transformers")
    if spec is not None and spec.submodule_search_locations:
        training_args_path = (
            Path(next(iter(spec.submodule_search_locations))) / "training_args.py"
        )
        try:
            training_args_tree = ast.parse(training_args_path.read_bytes())
        except (OSError, SyntaxError):
            pass
        else:
            for candidate in training_args_tree.body:
                if isinstance(candidate, ast.ClassDef) and candidate.name == (
                    "TrainingArguments"
                ):
                    supported = {
                        statement.target.id
                        for statement in candidate.body
                        if isinstance(statement, ast.AnnAssign)
                        and isinstance(statement.target, ast.Name)
                    }
                    break
    unsupported: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = (
            function.id
            if isinstance(function, ast.Name)
            else function.attr if isinstance(function, ast.Attribute) else ""
        )
        if name != "TrainingArguments":
            continue
        keywords = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
        unsupported.update(keywords & {"overwrite_output_dir"})
        if supported is not None:
            unsupported.update(keywords - supported)
    return sorted(unsupported)


def _unsafe_training_api_errors(tree: ast.AST) -> list[str]:
    """Reject target-environment API and batching failures before GPU launch."""
    errors: set[str] = set()
    loader_functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "from_pretrained"
            for child in ast.walk(node)
        )
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            name = (
                function.id
                if isinstance(function, ast.Name)
                else function.attr if isinstance(function, ast.Attribute) else ""
            )
            keywords = {kw.arg for kw in node.keywords if kw.arg is not None}
            if name in {"DPOTrainer", "DPOConfig"}:
                errors.add(
                    "DPOTrainer/DPOConfig is unavailable in the locked target "
                    "TRL/Transformers stack; use a compatible manual loss or SFTTrainer"
                )
            if name == "SFTTrainer" and "tokenizer" in keywords:
                errors.add(
                    "SFTTrainer(tokenizer=...) is unsupported by the target TRL "
                    "contract; use processing_class=tokenizer"
                )
            if name == "train" and "max_steps" in keywords:
                errors.add(
                    "Trainer.train(max_steps=...) is unsupported; set max_steps in "
                    "the trainer configuration"
                )
            if (
                name == "tensor"
                and isinstance(function, ast.Attribute)
                and isinstance(function.value, ast.Name)
                and function.value.id == "torch"
                and node.args
                and isinstance(node.args[0], ast.Subscript)
                and isinstance(node.args[0].value, ast.Name)
                and node.args[0].value.id == "batch"
            ):
                errors.add(
                    "torch.tensor(batch[...]) is unsafe with DataLoader-collated "
                    "sequence columns; configure torch formatting or stack the batch"
                )

        if isinstance(node, (ast.For, ast.AsyncFor)):
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                if (
                    isinstance(child.func, ast.Attribute)
                    and child.func.attr == "from_pretrained"
                ) or (
                    isinstance(child.func, ast.Name)
                    and child.func.id in loader_functions
                ):
                    errors.add(
                        "model/tokenizer from_pretrained loading may not occur inside "
                        "a per-item loop; load once and reuse the object"
                    )
                    break
    return sorted(errors)


def _undefined_name_errors(method_path: Path) -> list[str]:
    """Run the target environment's Ruff F821 analysis on generated code."""
    adjacent_ruff = Path(sys.executable).with_name("ruff")
    ruff = (
        str(adjacent_ruff)
        if os.access(adjacent_ruff, os.X_OK)
        else shutil.which("ruff")
    )
    if ruff is None:
        if os.environ.get("AAR_REQUIRE_METHOD_CONTRACT") == "1":
            return ["Ruff is required for fail-closed undefined-name validation"]
        return []
    completed = subprocess.run(
        [ruff, "check", "--select", "F821", "--output-format", "concise", str(method_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return []
    detail = completed.stdout.strip() or completed.stderr.strip()
    return ["undefined-name validation failed: " + detail[-4000:]]


def validate(
    method_path: Path,
    *,
    run_dry_run: bool = False,
    require_gemma4_targets: bool = False,
    require_smoke_run: bool = False,
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
            elif _gemma_regex_wrapped_in_collection(tree):
                errors.append(
                    "Gemma-4 PEFT target_modules regex must be passed as a string, "
                    "not a list, set, or tuple; PEFT treats collection entries as "
                    "literal module suffixes"
                )
        if require_smoke_run and not any(
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "config"
            and node.attr == "smoke_run"
            for node in ast.walk(tree)
        ):
            errors.append(
                "run_experiment must use config.smoke_run for the one-step real-GPU "
                "training path"
            )
        if require_smoke_run:
            unsupported_training_args = _unsupported_training_arguments(tree)
            if unsupported_training_args:
                errors.append(
                    "TrainingArguments uses keyword(s) unsupported by the target "
                    "Transformers contract: "
                    + ", ".join(unsupported_training_args)
                )
            errors.extend(_undefined_name_errors(method_path))
            errors.extend(_unsafe_training_api_errors(tree))

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
                if require_smoke_run:
                    config_kwargs["smoke_run"] = False
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
    parser.add_argument("--require-smoke-run", action="store_true")
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
            require_smoke_run=args.require_smoke_run,
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
