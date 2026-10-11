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
    target_thinking_value = os.getenv("AAR_TARGET_ENABLE_THINKING", "").strip().lower()
    if target_thinking_value not in {
        "",
        "0",
        "false",
        "no",
        "off",
        "1",
        "true",
        "yes",
        "on",
    }:
        errors.add("AAR_TARGET_ENABLE_THINKING must be a boolean value when set")
    target_thinking_required = target_thinking_value in {"1", "true", "yes", "on"}
    serve_v2_chat_completion_names: set[str] = {"chat_completion"}
    serve_v2_module_names: set[str] = set()
    chat_template_normalizer_names: set[str] = set()
    chat_template_module_names: set[str] = set()
    seq2seq_collator_names = {"DataCollatorForSeq2Seq"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "transformers":
            seq2seq_collator_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "DataCollatorForSeq2Seq"
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "aar.utils.chat_template"
        ):
            chat_template_normalizer_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "normalize_chat_template_ids"
            )
        elif isinstance(node, ast.ImportFrom) and node.module == "aar.utils":
            chat_template_module_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "chat_template"
            )
        elif isinstance(node, ast.Import):
            chat_template_module_names.update(
                alias.asname
                for alias in node.names
                if alias.name == "aar.utils.chat_template" and alias.asname
            )
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "aar.infrastructure.serve_v2"
        ):
            serve_v2_chat_completion_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "chat_completion"
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module == "aar.infrastructure"
        ):
            serve_v2_module_names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == "serve_v2"
            )
        elif isinstance(node, ast.Import):
            serve_v2_module_names.update(
                alias.asname
                for alias in node.names
                if alias.name == "aar.infrastructure.serve_v2" and alias.asname
            )

    def is_serve_v2_chat_completion_call(node: ast.Call) -> bool:
        function = node.func
        if (
            isinstance(function, ast.Name)
            and function.id in serve_v2_chat_completion_names
        ):
            return True
        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "chat_completion"
        ):
            return False
        if isinstance(function.value, ast.Name):
            return function.value.id in serve_v2_module_names
        value = function.value
        return (
            isinstance(value, ast.Attribute)
            and value.attr == "serve_v2"
            and isinstance(value.value, ast.Attribute)
            and value.value.attr == "infrastructure"
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == "aar"
        )

    def is_chat_template_normalizer_call(node: ast.Call) -> bool:
        function = node.func
        if (
            isinstance(function, ast.Name)
            and function.id in chat_template_normalizer_names
        ):
            return True
        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "normalize_chat_template_ids"
        ):
            return False
        if isinstance(function.value, ast.Name):
            return function.value.id in chat_template_module_names
        value = function.value
        return (
            isinstance(value, ast.Attribute)
            and value.attr == "chat_template"
            and isinstance(value.value, ast.Attribute)
            and value.value.attr == "utils"
            and isinstance(value.value.value, ast.Name)
            and value.value.value.id == "aar"
        )

    def is_seq2seq_collator_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        function = node.func
        return (
            isinstance(function, ast.Name)
            and function.id in seq2seq_collator_names
        ) or (
            isinstance(function, ast.Attribute)
            and function.attr == "DataCollatorForSeq2Seq"
        )

    seq2seq_collator_bindings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and is_seq2seq_collator_call(node.value):
            seq2seq_collator_bindings.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
            and is_seq2seq_collator_call(node.value)
        ):
            seq2seq_collator_bindings.add(node.target.id)
    sft_trainer_classes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Name) and base.id == "SFTTrainer")
            or (isinstance(base, ast.Attribute) and base.attr == "SFTTrainer")
            for base in node.bases
        )
    }
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

    def smoke_max_steps(value: ast.AST) -> int | None:
        if not isinstance(value, ast.IfExp):
            return None
        test = value.test
        if not (
            isinstance(test, ast.Attribute)
            and isinstance(test.value, ast.Name)
            and test.value.id == "config"
            and test.attr == "smoke_run"
        ):
            return None
        return value.body.value if isinstance(value.body, ast.Constant) else None

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "trl"
            and any(
                alias.name == "DataCollatorForCompletionOnlyLM"
                for alias in node.names
            )
        ):
            errors.add(
                "DataCollatorForCompletionOnlyLM is unavailable in locked TRL 0.21; "
                "use SFTConfig(completion_only_loss=True) with a prompt/completion "
                "dataset or implement a compatible collator"
            )
        if isinstance(node, ast.Call):
            function = node.func
            name = (
                function.id
                if isinstance(function, ast.Name)
                else function.attr if isinstance(function, ast.Attribute) else ""
            )
            keywords = {kw.arg for kw in node.keywords if kw.arg is not None}
            if is_chat_template_normalizer_call(node) and not any(
                isinstance(argument, ast.Starred) for argument in node.args
            ) and not any(keyword.arg is None for keyword in node.keywords):
                value_keywords = sum(
                    keyword.arg == "value" for keyword in node.keywords
                )
                unsupported_keywords = sorted(
                    keyword
                    for keyword in keywords
                    if keyword != "value"
                )
                supplied_values = len(node.args) + value_keywords
                if supplied_values != 1 or unsupported_keywords:
                    detail = (
                        f"received {len(node.args)} positional argument(s)"
                    )
                    if keywords:
                        detail += " and keyword(s): " + ", ".join(sorted(keywords))
                    errors.add(
                        "normalize_chat_template_ids accepts exactly one argument "
                        f"(value); {detail}"
                    )
            if is_serve_v2_chat_completion_call(node):
                supported = {
                    "deployment_dir",
                    "model",
                    "enable_thinking",
                    "max_tokens",
                    "temperature",
                    "timeout",
                }
                unsupported = sorted(keywords - supported)
                if len(node.args) > 1:
                    errors.add(
                        "chat_completion accepts exactly one positional argument "
                        "(messages); pass model= as a keyword"
                    )
                if unsupported:
                    errors.add(
                        "chat_completion keyword(s) are unsupported by the locked "
                        "Serve API client: "
                        + ", ".join(unsupported)
                    )
                keyword_values = {
                    keyword.arg: keyword.value
                    for keyword in node.keywords
                    if keyword.arg is not None
                }
                enable_thinking = keyword_values.get("enable_thinking")
                thinking_disabled = (
                    isinstance(enable_thinking, ast.Constant)
                    and enable_thinking.value is False
                )
                thinking_enabled = enable_thinking is None or (
                    isinstance(enable_thinking, ast.Constant)
                    and enable_thinking.value is True
                )
                if target_thinking_required and not thinking_enabled:
                    errors.add(
                        "AAR_TARGET_ENABLE_THINKING requires chat_completion to "
                        "omit enable_thinking (the client default is True) or pass "
                        "the literal enable_thinking=True"
                    )
                max_tokens = keyword_values.get("max_tokens")
                uses_context_aware_default = max_tokens is None or (
                    isinstance(max_tokens, ast.Constant)
                    and max_tokens.value is None
                )
                static_budget = (
                    max_tokens.value
                    if isinstance(max_tokens, ast.Constant)
                    and isinstance(max_tokens.value, int)
                    and not isinstance(max_tokens.value, bool)
                    else None
                )
                if (
                    not thinking_disabled
                    and not uses_context_aware_default
                    and (static_budget is None or static_budget < 8192)
                ):
                    errors.add(
                        "chat_completion with thinking enabled must omit "
                        "max_tokens (the client asks vLLM for the request's "
                        "context-aware maximum) or use a literal budget of at "
                        "least 8192 tokens"
                    )
            if name in {"DPOTrainer", "DPOConfig"}:
                errors.add(
                    "DPOTrainer/DPOConfig is unavailable in the locked target "
                    "TRL/Transformers stack; use a compatible manual loss or SFTTrainer"
                )
            if name in {"SFTTrainer", *sft_trainer_classes} and "tokenizer" in keywords:
                errors.add(
                    "SFTTrainer(tokenizer=...) is unsupported by the target TRL "
                    "contract; use processing_class=tokenizer"
                )
            if name in {"SFTTrainer", *sft_trainer_classes}:
                for keyword in node.keywords:
                    if keyword.arg != "data_collator":
                        continue
                    if is_seq2seq_collator_call(keyword.value) or (
                        isinstance(keyword.value, ast.Name)
                        and keyword.value.id in seq2seq_collator_bindings
                    ):
                        errors.add(
                            "SFTTrainer data_collator=DataCollatorForSeq2Seq(...) "
                            "is unsafe for causal-language-model SFT: an "
                            "input_ids-only dataset is padded with labels=None, so "
                            "the model returns logits without loss; omit "
                            "data_collator to use TRL's causal-LM collator or pass "
                            "a collator that emits non-None causal labels"
                        )
            if name == "SFTTrainer" and keywords & {
                "max_seq_length",
                "dataset_text_field",
            }:
                invalid = ", ".join(
                    sorted(keywords & {"max_seq_length", "dataset_text_field"})
                )
                errors.add(
                    f"SFTTrainer keyword(s) {invalid} are unsupported by locked TRL "
                    "0.21; use SFTConfig(max_length=..., dataset_text_field=...) "
                    "and pass it as args="
                )
            if name == "SFTConfig" and keywords & {
                "max_seq_length",
                "warmup_ratio",
            }:
                invalid = ", ".join(
                    sorted(keywords & {"max_seq_length", "warmup_ratio"})
                )
                errors.add(
                    f"SFTConfig keyword(s) {invalid} are unsupported by locked TRL "
                    "0.21; use max_length and warmup_steps"
                )
            for keyword in node.keywords:
                if keyword.arg == "max_steps":
                    value = smoke_max_steps(keyword.value)
                    if value is not None and value != 1:
                        errors.add(
                            "config.smoke_run must set max_steps=1, not "
                            f"{value}, for the required one-step GPU preflight"
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

        if isinstance(node, ast.Try) and any(
            isinstance(child, ast.Call)
            and (
                (
                    isinstance(child.func, ast.Name)
                    and child.func.id == "chat_completion"
                )
                or (
                    isinstance(child.func, ast.Name)
                    and child.func.id in {
                        function.name
                        for function in ast.walk(tree)
                        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and any(
                            isinstance(grandchild, ast.Call)
                            and isinstance(grandchild.func, ast.Name)
                            and grandchild.func.id == "chat_completion"
                            for grandchild in ast.walk(function)
                        )
                    }
                )
            )
            for child in node.body
            for child in ast.walk(child)
        ):
            for handler in node.handlers:
                catches_everything = handler.type is None or (
                    isinstance(handler.type, ast.Name)
                    and handler.type.id in {"Exception", "BaseException"}
                )
                reraises = any(isinstance(child, ast.Raise) for child in ast.walk(handler))
                if catches_everything and not reraises:
                    errors.add(
                        "chat_completion failures may not be swallowed by a broad "
                        "exception handler; target-data generation must fail closed"
                    )

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
            )
            if any(
                isinstance(target, ast.Name) and target.id == "max_steps"
                for target in targets
            ):
                smoke_steps = smoke_max_steps(value)
                if smoke_steps is not None and smoke_steps != 1:
                    errors.add(
                        "config.smoke_run must set max_steps=1, not "
                        f"{smoke_steps}, for the required one-step GPU preflight"
                    )
    return sorted(errors)


def _autodata_loader_errors(tree: ast.AST) -> list[str]:
    """Mirror the native proposal gate for receipt-producing AutoData loads."""
    try:
        expected_rows = int(os.getenv("AAR_AUTODATA_PRODUCTION_ROWS", "1000"))
    except ValueError:
        return ["AAR_AUTODATA_PRODUCTION_ROWS must be an integer"]
    string_literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    required_literals = {
        "AAR_CURRENT_RUN_ID",
        "TEAM_DIR",
        "training-handoff.json",
        "autodata-training-data-contract.json",
        "dataset",
        "production_execution_id",
        "training-consumption.json",
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        name = (
            function.id
            if isinstance(function, ast.Name)
            else function.attr if isinstance(function, ast.Attribute) else ""
        )
        if name != "load_autodata_campaign_datasets":
            continue
        keywords = {item.arg: item.value for item in node.keywords if item.arg}
        required = keywords.get("required_rows")
        if not isinstance(required, ast.Constant) or required.value != expected_rows:
            return [
                "AutoData loader must use literal "
                f"required_rows={expected_rows}"
            ]
        if "receipt_path" not in keywords:
            return ["AutoData loader must write a training consumption receipt"]
        if "expected_execution_ids" not in keywords:
            return ["AutoData loader must bind expected_execution_ids"]
        expected = keywords["expected_execution_ids"]
        if not isinstance(expected, (ast.List, ast.Tuple)) or len(expected.elts) != 1:
            return [
                "AutoData loader must bind exactly one production execution ID"
            ]
        if not (
            isinstance(expected.elts[0], ast.Name)
            and expected.elts[0].id == "production_execution_id"
        ):
            return ["AutoData loader must pass the verified production_execution_id"]
        execution_bindings: list[ast.AST] = []
        for candidate in ast.walk(tree):
            if isinstance(candidate, ast.Assign) and any(
                isinstance(target, ast.Name)
                and target.id == "production_execution_id"
                for target in candidate.targets
            ):
                execution_bindings.append(candidate.value)
            elif (
                isinstance(candidate, ast.AnnAssign)
                and isinstance(candidate.target, ast.Name)
                and candidate.target.id == "production_execution_id"
                and candidate.value is not None
            ):
                execution_bindings.append(candidate.value)
        if not execution_bindings or any(
            not any(
                isinstance(child, ast.Subscript)
                and isinstance(child.slice, ast.Constant)
                and child.slice.value == "production_execution_id"
                for child in ast.walk(binding)
            )
            for binding in execution_bindings
        ):
            return [
                "production_execution_id must come directly from the verified "
                "training handoff; placeholders and run-ID fallbacks are forbidden"
            ]
        if "judge_rubric" not in keywords:
            return ["AutoData loader must bind the content-addressed judge rubric"]
        objective = keywords.get("training_objective")
        if (
            not isinstance(objective, ast.Constant)
            or objective.value not in {"sft", "dpo"}
        ):
            return [
                "AutoData loader must declare literal training_objective='sft' or "
                "'dpo'"
            ]
        missing_literals = sorted(required_literals - string_literals)
        if missing_literals:
            return [
                "AutoData method must resolve the verified run handoff; missing "
                "literal(s): " + ", ".join(missing_literals)
            ]
        for candidate in ast.walk(tree):
            if not isinstance(candidate, ast.Try):
                continue
            if not any(
                isinstance(child, ast.Call)
                and (
                    isinstance(child.func, ast.Name)
                    and child.func.id == "load_autodata_campaign_datasets"
                    or isinstance(child.func, ast.Attribute)
                    and child.func.attr == "load_autodata_campaign_datasets"
                )
                for statement in candidate.body
                for child in ast.walk(statement)
            ):
                continue
            for handler in candidate.handlers:
                catches_everything = handler.type is None or (
                    isinstance(handler.type, ast.Name)
                    and handler.type.id in {"Exception", "BaseException"}
                )
                reraises = any(
                    isinstance(child, ast.Raise) for child in ast.walk(handler)
                )
                if catches_everything and not reraises:
                    return [
                        "AutoData loader failures may not be swallowed or replaced "
                        "with fallback training data"
                    ]
        return []
    return [
        "this AutoData-enabled run requires the method to consume the verified "
        "production export; call aar.infrastructure.autodata_dataset."
        "load_autodata_campaign_datasets (programmatic-only or fallback data does "
        "not satisfy this run contract)"
    ]


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
    require_autodata_loader: bool = False,
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
        if require_autodata_loader:
            errors.extend(_autodata_loader_errors(tree))

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

    requirements = {
        "run_dry_run": run_dry_run,
        "require_gemma4_targets": require_gemma4_targets,
        "require_smoke_run": require_smoke_run,
        "require_autodata_loader": require_autodata_loader,
    }
    return {
        "schema_version": 1,
        "status": "passed" if not errors else "failed",
        "method_path": str(method_path),
        "source_sha256": source_hash,
        "requirements": requirements,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("method_path", type=Path)
    parser.add_argument("--proof", type=Path)
    parser.add_argument("--run-dry-run", action="store_true")
    parser.add_argument("--require-gemma4-targets", action="store_true")
    parser.add_argument("--require-smoke-run", action="store_true")
    parser.add_argument("--require-autodata-loader", action="store_true")
    args = parser.parse_args()
    proof = args.proof or args.method_path.parent / ".aar-method-contract.json"
    requirements = {
        "run_dry_run": args.run_dry_run,
        "require_gemma4_targets": args.require_gemma4_targets,
        "require_smoke_run": args.require_smoke_run,
        "require_autodata_loader": args.require_autodata_loader,
    }
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
                "requirements": requirements,
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
            require_autodata_loader=args.require_autodata_loader,
        )
    except Exception as error:  # noqa: BLE001 - always leave a diagnostic proof
        result = {
            "schema_version": 1,
            "status": "failed",
            "method_path": str(args.method_path.resolve()),
            "source_sha256": "",
            "requirements": requirements,
            "errors": [f"validator failed: {type(error).__name__}: {error}"],
        }
    proof.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
