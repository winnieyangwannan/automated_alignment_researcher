"""Fail-closed loading and consumption records for AAR Autodata artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping


MANIFEST_SCHEMA = "aar.autodata.dataset/v1"
CONSUMPTION_SCHEMA = "aar.autodata.consumption/v1"
TRAINING_LINK_SCHEMA = "aar.autodata.training-link/v1"
_DIGEST_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_REQUIRED_PROVENANCE_FIELDS = (
    "idea_name",
    "method_code_sha256",
    "autodata_spec_sha256",
    "resource_profile",
    "resource_profile_sha256",
    "budget_scope_id",
    "study_id",
    "execution_id",
    "recipe_digest",
    "pipeline_digest",
    "training_view",
    "required_retained_rows",
    "counts",
    "models",
    "budget",
)


def autodata_required() -> bool:
    """Return whether this run must consume a fully bound Autodata dataset."""
    return os.getenv("AAR_AUTODATA_REQUIRED", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if parsed < 1 or str(parsed) != str(value).strip():
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _required_retained_rows() -> int | None:
    raw = os.getenv("AAR_AUTODATA_REQUIRED_RETAINED_ROWS", "").strip()
    return _positive_int(raw, "AAR_AUTODATA_REQUIRED_RETAINED_ROWS") if raw else None


def _artifact_dir(run_id: str) -> Path:
    team_dir = os.getenv("TEAM_DIR", "")
    if not team_dir:
        raise ValueError("TEAM_DIR is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,191}", run_id):
        raise ValueError("run_id contains unsupported characters")
    result = Path(team_dir).resolve() / "autodata" / run_id
    if result.is_symlink():
        raise ValueError("Autodata artifact directory must not be a symlink")
    return result


def _canonical_rows(rows: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()


def _validate_digest(value: Any, name: str) -> str:
    result = str(value or "").lower()
    if not _DIGEST_RE.fullmatch(result):
        raise ValueError(f"Autodata manifest {name} is not a SHA-256 digest")
    return result.removeprefix("sha256:")


def _decimal(value: Any, name: str, *, positive: bool) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError(f"Autodata manifest {name} must be a finite decimal") from error
    if not result.is_finite() or (result <= 0 if positive else result < 0):
        qualifier = "positive " if positive else "non-negative "
        raise ValueError(f"Autodata manifest {name} must be a {qualifier}finite decimal")
    return result


def _validate_row(row: Any, index: int, training_view: str, *, strict: bool) -> None:
    if not isinstance(row, dict):
        raise ValueError(f"Autodata row {index} is not an object")
    if training_view == "sft":
        keys = ("prompt", "response")
    elif training_view == "preference":
        keys = ("prompt", "chosen", "rejected")
    elif strict:
        raise ValueError(f"unsupported Autodata training_view: {training_view!r}")
    else:
        keys = ("prompt", "response")
    for key in keys:
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError(f"Autodata row {index} requires non-empty string {key!r}")


def validate_autodata_artifacts(
    rows: Any,
    manifest: Any,
    *,
    run_id: str,
    expected_pipeline_sha: str,
    expected_binding: Mapping[str, Any] | None = None,
    required: bool | None = None,
) -> bytes:
    """Validate an adapter response and return its canonical JSONL bytes."""
    strict = autodata_required() if required is None else required
    if not isinstance(rows, list) or not isinstance(manifest, dict):
        raise ValueError("Autodata artifacts require rows[] and manifest{}")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError("Autodata artifact manifest has an unsupported schema")
    if manifest.get("run_id") != run_id:
        raise ValueError("Autodata artifact manifest is bound to a different run_id")
    if str(manifest.get("pipeline_sha", "")).lower() != expected_pipeline_sha.lower():
        raise ValueError("Autodata manifest pipeline SHA does not match AAR_AUTODATA_SHA")

    if strict:
        missing = [key for key in _REQUIRED_PROVENANCE_FIELDS if key not in manifest]
        if missing:
            raise ValueError(
                "required Autodata manifest is missing provenance fields: "
                + ", ".join(missing)
            )
        for key in (
            "method_code_sha256",
            "autodata_spec_sha256",
            "resource_profile_sha256",
            "recipe_digest",
            "pipeline_digest",
        ):
            _validate_digest(manifest.get(key), key)
        if expected_binding:
            for key, expected in expected_binding.items():
                if expected is not None and manifest.get(key) != expected:
                    raise ValueError(f"Autodata manifest {key} does not match approved binding")
        expected_profile = os.getenv("AAR_AUTODATA_RESOURCE_PROFILE", "").strip()
        if expected_profile and manifest.get("resource_profile") != expected_profile:
            raise ValueError("Autodata manifest resource_profile does not match launch profile")
        expected_profile_digest = os.getenv(
            "AAR_AUTODATA_RESOURCE_PROFILE_SHA256", ""
        ).lower().removeprefix("sha256:")
        if (
            expected_profile_digest
            and _validate_digest(
                manifest.get("resource_profile_sha256"), "resource_profile_sha256"
            )
            != expected_profile_digest
        ):
            raise ValueError(
                "Autodata manifest resource_profile_sha256 does not match launch profile"
            )
        expected_scope = os.getenv("AAR_AUTODATA_BUDGET_SCOPE_ID", "").strip()
        if expected_scope and manifest.get("budget_scope_id") != expected_scope:
            raise ValueError("Autodata manifest budget_scope_id does not match launch scope")

    training_view = str(manifest.get("training_view") or "sft")
    seen_ids: set[str] = set()
    for index, row in enumerate(rows):
        _validate_row(row, index, training_view, strict=strict)
        row_id = row.get("id")
        if row_id is not None:
            if not isinstance(row_id, str) or not row_id:
                raise ValueError(f"Autodata row {index} has an invalid id")
            if row_id in seen_ids:
                raise ValueError(f"Autodata dataset has duplicate row id {row_id!r}")
            seen_ids.add(row_id)

    payload = _canonical_rows(rows)
    if manifest.get("row_count") != len(rows):
        raise ValueError("Autodata artifact manifest row_count mismatch")
    digest = hashlib.sha256(payload).hexdigest()
    if str(manifest.get("dataset_sha256", "")).removeprefix("sha256:") != digest:
        raise ValueError("Autodata dataset digest does not match its manifest")
    if not rows:
        raise ValueError("Autodata dataset is empty")

    required_rows = _required_retained_rows()
    if strict:
        manifest_required = _positive_int(
            manifest.get("required_retained_rows"), "manifest.required_retained_rows"
        )
        if required_rows is not None and manifest_required != required_rows:
            raise ValueError("manifest required_retained_rows does not match launch contract")
        if len(rows) < manifest_required:
            raise ValueError("Autodata dataset did not reach required_retained_rows")
        counts = manifest.get("counts")
        if not isinstance(counts, dict):
            raise ValueError("Autodata manifest counts must be an object")
        retained = counts.get("retained")
        if retained != len(rows):
            raise ValueError("Autodata manifest retained count does not match dataset")
        generated = counts.get("generated")
        rejected = counts.get("rejected")
        if not isinstance(generated, int) or not isinstance(rejected, int):
            raise ValueError("Autodata generated and rejected counts must be integers")
        if generated < len(rows) or rejected < 0:
            raise ValueError("Autodata generated/rejected counts are inconsistent")
        models = manifest.get("models")
        if not isinstance(models, dict) or not all(
            isinstance(models.get(role), dict) and models[role].get("identity")
            for role in ("generator", "judge")
        ):
            raise ValueError("Autodata manifest must identify generator and judge models")
        budget = manifest.get("budget")
        if not isinstance(budget, dict):
            raise ValueError("Autodata manifest budget must be an object")
        authorized = _decimal(budget.get("max_cost_usd"), "budget.max_cost_usd", positive=True)
        spent = _decimal(budget.get("spent_cost_usd"), "budget.spent_cost_usd", positive=False)
        if spent > authorized:
            raise ValueError("Autodata manifest spent cost exceeds authorized cost")
        expected_cap = os.getenv("AAR_AUTODATA_MAX_COST_USD", "").strip()
        if expected_cap and authorized != _decimal(
            expected_cap, "AAR_AUTODATA_MAX_COST_USD", positive=True
        ):
            raise ValueError("Autodata manifest budget cap does not match launch authorization")
        for key in ("model_calls", "input_tokens", "output_tokens"):
            value = budget.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"Autodata manifest budget.{key} must be a non-negative integer")
    elif required_rows is not None and len(rows) < required_rows:
        raise ValueError("Autodata dataset did not reach required retained row count")
    return payload


def _write_consumption_receipt(
    artifact_dir: Path, *, run_id: str, manifest: Mapping[str, Any], row_count: int
) -> dict[str, Any]:
    receipt_path = artifact_dir / "autodata_consumption.json"
    expected = {
        "schema": CONSUMPTION_SCHEMA,
        "run_id": run_id,
        "dataset_sha256": str(manifest["dataset_sha256"]).removeprefix("sha256:"),
        "row_count": row_count,
    }
    if receipt_path.exists():
        if receipt_path.is_symlink():
            raise ValueError("Autodata consumption receipt must not be a symlink")
        receipt = json.loads(receipt_path.read_text())
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError("existing Autodata consumption receipt does not match dataset")
        return receipt
    receipt = {**expected, "loaded_at_unix": time.time(), "consumer_pid": os.getpid()}
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(receipt_path, flags, 0o600)
    except FileExistsError:
        receipt = json.loads(receipt_path.read_text())
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError("concurrent Autodata consumption receipt does not match dataset")
        return receipt
    with os.fdopen(descriptor, "w") as output:
        json.dump(receipt, output, indent=2, sort_keys=True)
        output.write("\n")
    return receipt


def _read_verified_dataset(
    run_id: str | None = None,
) -> tuple[str, Path, list[dict[str, Any]], dict[str, Any]]:
    resolved_run_id = run_id or os.getenv("AAR_CURRENT_RUN_ID", "")
    if not resolved_run_id:
        raise ValueError("run_id or AAR_CURRENT_RUN_ID is required")
    artifact_dir = _artifact_dir(resolved_run_id)
    rows_path = artifact_dir / "autodata_rows.jsonl"
    manifest_path = artifact_dir / "autodata_manifest.json"
    if not rows_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"verified Autodata artifacts are missing for run {resolved_run_id}")
    if rows_path.is_symlink() or manifest_path.is_symlink():
        raise ValueError("Autodata artifact files must not be symlinks")
    manifest = json.loads(manifest_path.read_text())
    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    expected_sha = os.getenv("AAR_AUTODATA_SHA", "").lower()
    if not expected_sha:
        raise ValueError("AAR_AUTODATA_SHA is required")
    payload = validate_autodata_artifacts(
        rows,
        manifest,
        run_id=resolved_run_id,
        expected_pipeline_sha=expected_sha,
    )
    if rows_path.read_bytes() != payload:
        raise ValueError("Autodata rows are not in canonical verified JSONL form")
    return resolved_run_id, artifact_dir, rows, manifest


def verify_autodata_dataset(run_id: str | None = None) -> dict[str, Any]:
    """Verify fetched artifacts without marking them consumed by method code."""
    resolved_run_id, _, rows, manifest = _read_verified_dataset(run_id)
    return {
        "run_id": resolved_run_id,
        "dataset_sha256": str(manifest["dataset_sha256"]).removeprefix("sha256:"),
        "row_count": len(rows),
        "training_view": manifest.get("training_view", "sft"),
    }


def load_autodata_dataset(run_id: str | None = None) -> list[dict[str, Any]]:
    """Load and record consumption of a verified run-bound Autodata dataset."""
    resolved_run_id, artifact_dir, rows, manifest = _read_verified_dataset(run_id)
    _write_consumption_receipt(
        artifact_dir, run_id=resolved_run_id, manifest=manifest, row_count=len(rows)
    )
    return rows


def verify_autodata_consumption(run_id: str | None = None) -> dict[str, Any]:
    """Verify that training recorded consumption of the current dataset digest."""
    resolved_run_id = run_id or os.getenv("AAR_CURRENT_RUN_ID", "")
    if not resolved_run_id:
        raise ValueError("run_id or AAR_CURRENT_RUN_ID is required")
    artifact_dir = _artifact_dir(resolved_run_id)
    receipt_path = artifact_dir / "autodata_consumption.json"
    manifest_path = artifact_dir / "autodata_manifest.json"
    if not receipt_path.is_file() or receipt_path.is_symlink():
        raise FileNotFoundError(f"Autodata consumption receipt is missing for run {resolved_run_id}")
    manifest = json.loads(manifest_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    expected_digest = str(manifest.get("dataset_sha256", "")).removeprefix("sha256:")
    if receipt.get("schema") != CONSUMPTION_SCHEMA:
        raise ValueError("unsupported Autodata consumption receipt schema")
    if receipt.get("run_id") != resolved_run_id:
        raise ValueError("Autodata consumption receipt run_id mismatch")
    if receipt.get("dataset_sha256") != expected_digest:
        raise ValueError("Autodata consumption receipt dataset digest mismatch")
    if receipt.get("row_count") != manifest.get("row_count"):
        raise ValueError("Autodata consumption receipt row count mismatch")
    return receipt


def autodata_training_link(run_id: str | None = None) -> dict[str, Any]:
    """Build the immutable dataset-to-training link for a model submission.

    This succeeds only after method code loaded the verified dataset.  The
    returned object is safe to copy into submission, score, and result metadata:
    it contains provenance identifiers, never training rows or credentials.
    """
    dataset = verify_autodata_dataset(run_id)
    receipt = verify_autodata_consumption(dataset["run_id"])
    return {
        "schema": TRAINING_LINK_SCHEMA,
        "run_id": dataset["run_id"],
        "dataset_sha256": dataset["dataset_sha256"],
        "row_count": dataset["row_count"],
        "training_view": dataset["training_view"],
        "consumption_receipt_schema": receipt["schema"],
    }


def record_autodata_training_link(
    link: Mapping[str, Any], *, model_submission_ref: str
) -> dict[str, Any]:
    """Persist a first-write-wins record linking a dataset to a submitted model."""
    run_id = str(link.get("run_id") or "")
    expected = autodata_training_link(run_id)
    if dict(link) != expected:
        raise ValueError("Autodata training link does not match verified consumption")
    record = {
        **expected,
        "model_submission_ref": str(model_submission_ref),
        "submitted_at_unix": time.time(),
    }
    path = _artifact_dir(run_id) / "autodata_training_link.json"
    if path.exists():
        if path.is_symlink():
            raise ValueError("Autodata training link must not be a symlink")
        existing = json.loads(path.read_text())
        for key, value in record.items():
            if key == "submitted_at_unix":
                continue
            if existing.get(key) != value:
                raise ValueError("existing Autodata training link does not match submission")
        return existing
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(record, output, indent=2, sort_keys=True)
        output.write("\n")
    return record
