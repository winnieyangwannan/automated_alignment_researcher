"""Backend-neutral reconciliation from verified AutoData handoff to training smoke."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping


PROTECTED_SUBMISSION_FILES = (
    "scripts/submit_train_job.sh",
    "scripts/slurm_train_submit.sh",
    "scripts/aar_runtime_env.sh",
    "scripts/validate_method_contract.py",
)

_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")
_IDEA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TERMINAL_FAILURES = {
    "BOOT_FAIL",
    "CANCELLED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "REVOKED",
    "SPECIAL_EXIT",
    "TIMEOUT",
}


class TrainingSmokeCoordinatorError(RuntimeError):
    """Typed trusted-host failure with an explicit retry disposition."""

    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class TrainingSmokeOutcome:
    state: str
    run_id: str
    job_id: str | None
    terminal_receipt: Path | None = None


def _json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
        raise TrainingSmokeCoordinatorError(
            "training_smoke_evidence_invalid", f"{label} is unavailable"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TrainingSmokeCoordinatorError(
            "training_smoke_evidence_invalid", f"{label} is invalid"
        ) from error
    if not isinstance(value, dict):
        raise TrainingSmokeCoordinatorError(
            "training_smoke_evidence_invalid", f"{label} is not an object"
        )
    return value


def _atomic_private_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(dict(value), stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def training_job_id(team_dir: Path, run_id: str) -> str | None:
    """Read one final submission receipt without trusting shell evaluation."""

    receipt = team_dir / ".train_submissions" / f"{run_id}.env"
    if not receipt.exists() and not receipt.is_symlink():
        return None
    if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_size > 4096:
        raise TrainingSmokeCoordinatorError(
            "training_submission_receipt_invalid",
            "training submission receipt is unsafe",
        )
    try:
        lines = receipt.read_text(encoding="utf-8").splitlines()
        pairs = [line.split("=", 1) for line in lines if line]
        if any(len(pair) != 2 for pair in pairs):
            raise ValueError("malformed receipt line")
        values = dict(pairs)
    except (OSError, UnicodeError, ValueError) as error:
        raise TrainingSmokeCoordinatorError(
            "training_submission_receipt_invalid",
            "training submission receipt is invalid",
        ) from error
    job_id = values.get("job_id")
    if (
        set(values) != {"run_id", "job_id"}
        or values.get("run_id") != run_id
        or not isinstance(job_id, str)
        or re.fullmatch(r"[0-9]+", job_id) is None
    ):
        raise TrainingSmokeCoordinatorError(
            "training_submission_receipt_invalid",
            "training submission receipt does not match this run",
        )
    return job_id


def verify_protected_submission_files(repo: Path) -> None:
    """Require submission code to match the detached Git snapshot exactly."""

    for relative in PROTECTED_SUBMISSION_FILES:
        try:
            committed = subprocess.run(
                ["git", "show", f"HEAD:{relative}"],
                cwd=repo,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise TrainingSmokeCoordinatorError(
                "protected_file_verification_failed",
                "cannot verify protected training submission files",
            ) from error
        path = repo / relative
        if committed.returncode != 0 or path.is_symlink() or not path.is_file():
            raise TrainingSmokeCoordinatorError(
                "protected_file_verification_failed",
                "protected training submission file is unavailable",
            )
        if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(
            committed.stdout
        ).digest():
            raise TrainingSmokeCoordinatorError(
                "protected_file_hash_mismatch",
                "protected training submission file differs from Git",
            )
        if path.suffix == ".sh":
            syntax = subprocess.run(
                ["bash", "-n", str(path)],
                cwd=repo,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
            if syntax.returncode != 0:
                raise TrainingSmokeCoordinatorError(
                    "protected_file_syntax_invalid",
                    "protected training submission shell is invalid",
                )


class TrainingSmokeCoordinator:
    """Idempotently submit and verify exactly one optimizer-step training job."""

    def __init__(
        self,
        *,
        repo: Path,
        team_dir: Path,
        required_rows: int,
        submission_timeout_seconds: float = 120,
        completion_grace_seconds: float = 120,
        preflight_verifier: Callable[[str], Mapping[str, Any]] | None = None,
        method_hasher: Callable[[str], str | None] | None = None,
        protected_verifier: Callable[[Path], None] = verify_protected_submission_files,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        scheduler_reader: Callable[[str], str | None] | None = None,
    ) -> None:
        if (
            required_rows < 1
            or submission_timeout_seconds <= 0
            or completion_grace_seconds < 0
        ):
            raise ValueError("training smoke coordinator bounds are invalid")
        self.repo = repo.resolve(strict=True)
        self.team_dir = team_dir.resolve(strict=True)
        self.required_rows = required_rows
        self.submission_timeout_seconds = submission_timeout_seconds
        self.completion_grace_seconds = completion_grace_seconds
        self.preflight_verifier = preflight_verifier or self._verify_preflight
        self.method_hasher = method_hasher or self._method_hash
        self.protected_verifier = protected_verifier
        self.command_runner = command_runner
        self.scheduler_reader = scheduler_reader or self._scheduler_state
        self._completed_without_marker_since: dict[str, float] = {}

    @staticmethod
    def _verify_preflight(run_id: str) -> Mapping[str, Any]:
        from aar.infrastructure.autodata_lifecycle import verify_preflight

        return verify_preflight(run_id)

    @staticmethod
    def _method_hash(idea_name: str) -> str | None:
        from aar.research_loop.tools.server_api_tools import _method_code

        _code, digest = _method_code(idea_name)
        return digest

    @staticmethod
    def _scheduler_state(job_id: str) -> str | None:
        try:
            completed = subprocess.run(
                ["sacct", "-j", job_id, "-X", "-n", "-P", "-o", "State"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        for line in completed.stdout.splitlines():
            state = line.strip().split("|", 1)[0].split()[0].rstrip("+").upper()
            if state:
                return state
        return None

    def _verified_handoff(
        self,
        run_id: str,
        *,
        meta_execution_id: str,
        production_execution_id: str,
    ) -> Mapping[str, Any]:
        verification = self.preflight_verifier(run_id)
        if (
            verification.get("schema") != "aar.autodata.lifecycle-verification/v1"
            or verification.get("run_id") != run_id
            or verification.get("meta_execution_id") != meta_execution_id
            or verification.get("production_execution_id") != production_execution_id
            or isinstance(verification.get("available_rows"), bool)
            or not isinstance(verification.get("available_rows"), int)
            or int(verification["available_rows"]) < self.required_rows
            or not isinstance(verification.get("dataset_sha256"), str)
        ):
            raise TrainingSmokeCoordinatorError(
                "training_handoff_invalid",
                "verified production handoff does not satisfy training smoke",
            )
        timing = verification.get("timing")
        if (
            not isinstance(timing, dict)
            or timing.get("schema") != "aar.autodata.lifecycle-timing/v1"
            or timing.get("run_id") != run_id
        ):
            raise TrainingSmokeCoordinatorError(
                "training_handoff_invalid",
                "verified production handoff has no lifecycle timing",
            )
        return verification

    def _submit(self, run_id: str, idea_name: str, expected_code_hash: str) -> str:
        if self.method_hasher(idea_name) != expected_code_hash:
            raise TrainingSmokeCoordinatorError(
                "training_method_hash_mismatch",
                "approved method changed before training submission",
            )
        self.protected_verifier(self.repo)
        try:
            completed = self.command_runner(
                [
                    "bash",
                    str(self.repo / "scripts" / "submit_train_job.sh"),
                    idea_name,
                    run_id,
                ],
                cwd=self.repo,
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.submission_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise TrainingSmokeCoordinatorError(
                "training_submission_timeout",
                "training submission wrapper timed out",
                retryable=True,
            ) from error
        job_id = completed.stdout.strip()
        if completed.returncode != 0 or re.fullmatch(r"[0-9]+", job_id) is None:
            raise TrainingSmokeCoordinatorError(
                "training_submission_failed",
                f"training submission wrapper exited with status {completed.returncode}",
                retryable=completed.returncode == 75,
            )
        receipt_job_id = training_job_id(self.team_dir, run_id)
        if receipt_job_id != job_id:
            raise TrainingSmokeCoordinatorError(
                "training_submission_receipt_missing",
                "training submission did not publish its final receipt",
            )
        return job_id

    def _publish_terminal_receipt(
        self,
        run_id: str,
        job_id: str,
        verification: Mapping[str, Any],
    ) -> Path:
        smoke_path = self.team_dir / "method_smoke" / f"{run_id}.passed.json"
        smoke = _json_object(smoke_path, "training smoke result")
        consumption = smoke.get("autodata_consumption")
        if (
            smoke.get("schema_version") != 1
            or smoke.get("status") != "passed"
            or smoke.get("run_id") != run_id
            or smoke.get("smoke_run") is not True
            or smoke.get("optimizer_steps") != 1
            or smoke.get("slurm_job_id") != job_id
            or not isinstance(consumption, dict)
            or consumption.get("run_id") != run_id
            or consumption.get("consumed_rows") != self.required_rows
            or consumption.get("required_rows") != self.required_rows
            or consumption.get("dataset_sha256") != verification.get("dataset_sha256")
            or consumption.get("production_execution_id")
            != verification.get("production_execution_id")
        ):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_result_invalid",
                "training smoke result does not prove exact AutoData consumption",
            )
        model_raw = smoke.get("model_path")
        weight_name = smoke.get("adapter_weight_file")
        receipt_raw = consumption.get("consumption_receipt")
        timing_raw = smoke.get("phase_timings")
        if not all(
            isinstance(value, str) and value
            for value in (model_raw, weight_name, receipt_raw, timing_raw)
        ):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_result_invalid",
                "training smoke result has incomplete evidence",
            )
        paths = [Path(str(value)) for value in (model_raw, receipt_raw, timing_raw)]
        if any(path.is_symlink() for path in paths):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_result_invalid", "training smoke evidence is unsafe"
            )
        model_path, consumption_path, phase_timings_path = (
            path.resolve(strict=True) for path in paths
        )
        team = self.team_dir.resolve(strict=True)
        if any(
            team not in path.parents
            for path in (model_path, consumption_path, phase_timings_path)
        ):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_result_invalid",
                "training smoke evidence is outside the team directory",
            )
        weight_path = model_path / str(weight_name)
        if (
            weight_path.is_symlink()
            or not weight_path.is_file()
            or weight_path.resolve(strict=True).parent != model_path
            or weight_path.stat().st_size <= 0
        ):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_result_invalid",
                "training smoke adapter weight is empty or unsafe",
            )
        timing_path = self.team_dir / "autodata" / run_id / "autodata-lifecycle-timing.json"
        timing = verification["timing"]
        if timing_path.exists() or timing_path.is_symlink():
            if _json_object(timing_path, "lifecycle timing") != timing:
                raise TrainingSmokeCoordinatorError(
                    "training_smoke_result_invalid", "lifecycle timing changed"
                )
        else:
            _atomic_private_json(timing_path, timing)
        marker = self.team_dir / "autodata" / run_id / "training-smoke-canary-complete.json"
        payload = {
            "schema": "aar.autodata.training-smoke-canary-complete/v1",
            "run_id": run_id,
            "stop_after": "training_smoke",
            "required_accepted_rows": self.required_rows,
            "verification": dict(verification),
            "timing_report": str(timing_path),
            "training": {
                "job_id": job_id,
                "optimizer_steps": 1,
                "consumed_rows": consumption["consumed_rows"],
                "consumption_receipt": str(consumption_path),
                "phase_timings": str(phase_timings_path),
                "method_smoke_marker": str(smoke_path),
                "model_path": str(model_path),
                "adapter_weight_file": weight_name,
                "adapter_weight_sha256": hashlib.sha256(
                    weight_path.read_bytes()
                ).hexdigest(),
            },
        }
        if marker.exists() or marker.is_symlink():
            if _json_object(marker, "training smoke terminal receipt") != payload:
                raise TrainingSmokeCoordinatorError(
                    "training_smoke_receipt_mismatch",
                    "training smoke terminal receipt changed",
                )
        else:
            _atomic_private_json(marker, payload)
        return marker

    def reconcile(
        self,
        *,
        run_id: str,
        idea_name: str,
        expected_code_hash: str,
        meta_execution_id: str,
        production_execution_id: str,
    ) -> TrainingSmokeOutcome:
        if (
            _RUN_ID.fullmatch(run_id) is None
            or _IDEA_NAME.fullmatch(idea_name) is None
            or _SHA256.fullmatch(expected_code_hash) is None
        ):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_identity_invalid",
                "training smoke identity is invalid",
            )
        verification = self._verified_handoff(
            run_id,
            meta_execution_id=meta_execution_id,
            production_execution_id=production_execution_id,
        )
        job_id = training_job_id(self.team_dir, run_id)
        smoke_path = self.team_dir / "method_smoke" / f"{run_id}.passed.json"
        if job_id is None:
            if smoke_path.exists() or smoke_path.is_symlink():
                raise TrainingSmokeCoordinatorError(
                    "training_smoke_result_unbound",
                    "training smoke result exists without a submission receipt",
                )
            job_id = self._submit(run_id, idea_name, expected_code_hash)
            return TrainingSmokeOutcome("submitted", run_id, job_id)
        scores_raw = os.environ.get("SCORES_DIR", "").strip()
        failure_path = (
            Path(scores_raw) / f"{run_id}.failed.json" if scores_raw else None
        )
        if failure_path is not None and (
            failure_path.is_file() or failure_path.is_symlink()
        ):
            raise TrainingSmokeCoordinatorError(
                "training_smoke_failed", "training smoke published a failure marker"
            )
        if smoke_path.is_file() and not smoke_path.is_symlink():
            receipt = self._publish_terminal_receipt(run_id, job_id, verification)
            return TrainingSmokeOutcome("complete", run_id, job_id, receipt)
        state = self.scheduler_reader(job_id)
        if state in _TERMINAL_FAILURES:
            raise TrainingSmokeCoordinatorError(
                "training_smoke_job_failed",
                f"training smoke job ended in {state}",
                retryable=state in {"BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED"},
            )
        if state == "COMPLETED":
            started = self._completed_without_marker_since.setdefault(
                job_id, time.monotonic()
            )
            if time.monotonic() - started >= self.completion_grace_seconds:
                raise TrainingSmokeCoordinatorError(
                    "training_smoke_marker_missing",
                    "training completed without its one-step result marker",
                )
        else:
            self._completed_without_marker_since.pop(job_id, None)
        return TrainingSmokeOutcome("waiting", run_id, job_id)
