"""Durable HTTP boundary for AAR-triggered unattended AutoData lifecycles."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import traceback
import uuid
import fcntl
import stat
from abc import ABC, abstractmethod
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def _tree_digest(root: Path) -> str:
    members = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }
    return hashlib.sha256(_canonical_json(members)).hexdigest()


class CampaignBudgetLedger:
    """Atomic campaign-wide authorization, reservation, and usage ledger."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _paths(self, scope_id: str) -> tuple[Path, Path]:
        if not scope_id or not all(c.isalnum() or c in "._-" for c in scope_id):
            raise ValueError("budget_scope_id contains unsupported characters")
        return self.root / f"{scope_id}.json", self.root / f"{scope_id}.lock"

    def _locked(self, scope_id: str):
        _, lock_path = self._paths(scope_id)
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        return descriptor

    @staticmethod
    def _decimal(value: Any, name: str, *, positive: bool = False) -> Decimal:
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{name} must be a finite decimal") from exc
        if not result.is_finite() or result < 0 or (positive and result <= 0):
            raise ValueError(f"{name} must be {'positive' if positive else 'non-negative'}")
        return result

    def register(self, controls: Mapping[str, Any]) -> dict[str, Any]:
        scope_id = str(controls["budget_scope_id"])
        state_path, _ = self._paths(scope_id)
        descriptor = self._locked(scope_id)
        try:
            cap = self._decimal(
                controls["max_cost_usd"], "max_cost_usd", positive=True
            )
            expected = {
                "budget_scope_id": scope_id,
                "max_cost_usd": format(cap.normalize(), "f"),
                "resource_profile": str(controls["resource_profile"]),
                "resource_profile_sha256": str(controls["resource_profile_sha256"]),
            }
            if state_path.is_file():
                state = json.loads(state_path.read_text())
                if any(state.get(key) != value for key, value in expected.items()):
                    raise ValueError("budget scope already exists with a different cap or profile")
                return state
            state = {
                **expected,
                "spent_cost_usd": "0",
                "reserved_cost_usd": "0",
                "model_calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "reservations": {},
            }
            _write_json(state_path, state)
            return state
        finally:
            os.close(descriptor)

    def reserve(self, scope_id: str, maximum_cost: Any) -> str:
        amount = self._decimal(maximum_cost, "maximum_cost", positive=True)
        state_path, _ = self._paths(scope_id)
        descriptor = self._locked(scope_id)
        try:
            state = json.loads(state_path.read_text())
            cap = self._decimal(state["max_cost_usd"], "max_cost_usd")
            spent = self._decimal(state["spent_cost_usd"], "spent_cost_usd")
            reserved = self._decimal(state["reserved_cost_usd"], "reserved_cost_usd")
            if spent + reserved + amount > cap:
                raise RuntimeError("campaign budget cannot reserve this model call")
            reservation_id = "reserve_" + uuid.uuid4().hex
            state["reservations"][reservation_id] = str(amount)
            state["reserved_cost_usd"] = str(reserved + amount)
            _write_json(state_path, state)
            return reservation_id
        finally:
            os.close(descriptor)

    def settle(
        self,
        scope_id: str,
        reservation_id: str,
        *,
        actual_cost: Any | None,
        model_calls: int,
        input_tokens: int,
        output_tokens: int,
    ) -> dict[str, Any]:
        state_path, _ = self._paths(scope_id)
        descriptor = self._locked(scope_id)
        try:
            state = json.loads(state_path.read_text())
            reserved_amount = self._decimal(
                state["reservations"].pop(reservation_id), "reservation"
            )
            # Unknown failed-provider spend is charged at the full reservation.
            charged = (
                reserved_amount
                if actual_cost is None
                else self._decimal(actual_cost, "actual_cost")
            )
            spent = self._decimal(state["spent_cost_usd"], "spent_cost_usd") + charged
            reserved = self._decimal(state["reserved_cost_usd"], "reserved_cost_usd")
            state["spent_cost_usd"] = str(spent)
            state["reserved_cost_usd"] = str(reserved - reserved_amount)
            for key, value in {
                "model_calls": model_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }.items():
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{key} must be a non-negative integer")
                state[key] = int(state[key]) + value
            _write_json(state_path, state)
            if charged > reserved_amount:
                raise RuntimeError("provider exceeded its conservative per-call reservation")
            if spent > self._decimal(state["max_cost_usd"], "max_cost_usd"):
                raise RuntimeError("campaign budget was exceeded")
            return state
        finally:
            os.close(descriptor)

    def snapshot(self, scope_id: str) -> dict[str, Any]:
        state_path, _ = self._paths(scope_id)
        descriptor = self._locked(scope_id)
        try:
            return json.loads(state_path.read_text())
        finally:
            os.close(descriptor)

    def record_unreserved(
        self,
        scope_id: str,
        *,
        actual_cost: Any,
        model_calls: int,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Account a protocol-violating call before failing the run closed."""
        state_path, _ = self._paths(scope_id)
        descriptor = self._locked(scope_id)
        try:
            state = json.loads(state_path.read_text())
            cost = self._decimal(actual_cost, "actual_cost")
            state["spent_cost_usd"] = str(
                self._decimal(state["spent_cost_usd"], "spent_cost_usd") + cost
            )
            for key, value in {
                "model_calls": model_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }.items():
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{key} must be a non-negative integer")
                state[key] = int(state[key]) + value
            _write_json(state_path, state)
        finally:
            os.close(descriptor)


class LifecycleBackend(ABC):
    """Operator-owned backend boundary; live Kimi/Luna routing plugs in here."""

    @abstractmethod
    def run(self, job_root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
        """Return rows, manifest_fields, and status_fields."""

    @property
    @abstractmethod
    def models(self) -> Mapping[str, Mapping[str, Any]]:
        """Operator-pinned generator and judge identities."""

    @property
    def interactive(self) -> bool:
        return False

    @property
    def resource_evidence_binding(self) -> Mapping[str, str]:
        return {}

    def create_workspace(
        self,
        job_root: Path,
        request: Mapping[str, Any],
        ledger: CampaignBudgetLedger,
    ) -> dict[str, Any]:
        raise RuntimeError("backend does not expose workspace actions")

    def step_interactive(
        self,
        job_root: Path,
        request: Mapping[str, Any],
        ledger: CampaignBudgetLedger,
    ) -> dict[str, Any]:
        raise RuntimeError("backend does not expose workspace actions")

    def action_interactive(
        self,
        operation: str,
        job_root: Path,
        request: Mapping[str, Any],
        action_id: str,
        payload: Mapping[str, Any],
        ledger: CampaignBudgetLedger,
    ) -> dict[str, Any]:
        raise RuntimeError("backend does not expose workspace actions")


class DeterministicLifecycleBackend(LifecycleBackend):
    """Invoke the single canonical workspace -> meta -> production smoke driver."""

    def __init__(
        self,
        *,
        checkout: Path,
        recipe_root: Path,
        driver_script: Path,
        row_transform: str = "native",
        python: str | None = None,
    ) -> None:
        self.checkout = checkout.resolve()
        self.recipe_root = recipe_root.resolve()
        self.driver_script = driver_script.resolve()
        self.row_transform = row_transform
        self.python = python or sys.executable
        if self.recipe_root != self.checkout and self.checkout not in self.recipe_root.parents:
            raise ValueError("operator recipe_root must be contained in the pinned checkout")
        if not self.recipe_root.is_dir() or not self.driver_script.is_file():
            raise ValueError("operator recipe or lifecycle driver is missing")

    def _rows(self, items: list[Any], view: str) -> list[dict[str, Any]]:
        if self.row_transform == "toy_sft":
            return [
                {
                    "id": str(item["task_id"]),
                    "prompt": f"Return twice the number {item['input']}.",
                    "response": str(item["target"]),
                    "native_item": item,
                }
                for item in items
            ]
        if self.row_transform != "native":
            raise ValueError(f"unsupported operator row transform {self.row_transform!r}")
        rows = [dict(item) for item in items if isinstance(item, dict)]
        fields = ("prompt", "response") if view == "sft" else ("prompt", "chosen", "rejected")
        if view not in {"sft", "preference"} or any(
            not all(isinstance(row.get(key), str) and row[key].strip() for key in fields)
            for row in rows
        ):
            raise ValueError("native rows do not satisfy the operator-approved training view")
        return rows

    @property
    def models(self) -> Mapping[str, Mapping[str, Any]]:
        return {
            "generator": {"identity": "deterministic-template"},
            "judge": {"identity": "deterministic-checks"},
        }

    def run(self, job_root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
        spec = request["spec"]
        forbidden = {
            "action_provider",
            "driver_path",
            "production_execution_path",
            "recipe_path",
            "row_transform",
        } & set(spec)
        if forbidden:
            raise ValueError(
                "operator-controlled fields are forbidden in AUTODATA_SPEC: "
                + ", ".join(sorted(forbidden))
            )
        output = job_root / "native-lifecycle"
        completed = subprocess.run(
            [
                self.python,
                str(self.driver_script),
                "--autodata-root",
                str(self.checkout),
                "--output-root",
                str(output),
                "--run-id",
                str(request["run_id"]),
            ],
            cwd=self.driver_script.parents[1],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10800,
            check=False,
        )
        (job_root / "driver.stdout").write_text(completed.stdout)
        (job_root / "driver.stderr").write_text(completed.stderr)
        if completed.returncode:
            detail = completed.stderr.strip() or completed.stdout[-2000:]
            raise RuntimeError(f"unattended lifecycle failed ({completed.returncode}): {detail}")
        report = json.loads((output / "e2e_report.json").read_text())
        native_rows = [
            json.loads(line)
            for line in (output / "autodata_rows.jsonl").read_text().splitlines()
            if line.strip()
        ]
        rows = self._rows(native_rows, str(spec.get("training_view", "sft")))
        workspace_id = str(report["workspace_created"]["workspace_id"])
        production = report["production"]
        meta = report["meta_optimize"]
        return {
            "rows": rows,
            "manifest_fields": {
                "study_id": str(report.get("study_id", f"unattended:{workspace_id}")),
                "execution_id": str(production["execution_id"]),
                "recipe_digest": _tree_digest(self.recipe_root),
                "pipeline_digest": hashlib.sha256(
                    (self.recipe_root / "autodata.pipeline.json").read_bytes()
                ).hexdigest(),
                "workspace_id": workspace_id,
                "meta_optimize_execution_id": str(meta["execution_id"]),
                "production_execution_id": str(production["execution_id"]),
                "meta_optimize_source_task_count": meta["source_task_count"],
                "production_source_task_count": production["source_task_count"],
                "modes_completed_in_order": ["meta_optimize", "production"],
                "approval_principal": "aar-integrity-monitor",
                "action_provider": "deterministic-local-test",
                "unattended": True,
            },
            "status_fields": {
                "workspace_id": workspace_id,
                "meta_execution_id": str(meta["execution_id"]),
                "production_execution_id": str(production["execution_id"]),
            },
        }


class LiveModelLifecycleBackend(LifecycleBackend):
    """Fail-closed seam for an operator-supplied Kimi/Luna lifecycle driver.

    The driver owns provider calls and must return metered usage. Credentials
    remain in its environment and are never serialized into the AAR request.
    """

    def __init__(
        self,
        *,
        driver_script: Path,
        generator_model: str,
        judge_model: str,
        generator_url: str,
        judge_url: str,
        generator_token_env: str,
        judge_token_env: str,
        model_canary_report: Path,
        resource_profile_path: Path,
        generator_deployment_id: str = "",
        max_wall_seconds: int = 10800,
        python: str | None = None,
    ) -> None:
        self.driver_script = driver_script.resolve()
        self.python = python or sys.executable
        self.generator_model = generator_model.strip()
        self.judge_model = judge_model.strip()
        self.generator_url = generator_url.strip()
        self.judge_url = judge_url.strip()
        self.generator_token_env = generator_token_env.strip()
        self.judge_token_env = judge_token_env.strip()
        self.generator_deployment_id = generator_deployment_id.strip()
        self.model_canary_report = Path(
            os.path.abspath(model_canary_report.expanduser())
        )
        self.resource_profile_path = Path(
            os.path.abspath(resource_profile_path.expanduser())
        )
        for label, path, owner_only in (
            ("model canary report", self.model_canary_report, True),
            ("resource profile", self.resource_profile_path, False),
        ):
            try:
                info = path.lstat()
            except OSError as exc:
                raise ValueError(f"live AutoData {label} is unavailable") from exc
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise ValueError(f"live AutoData {label} must be a regular file")
            if info.st_uid != os.geteuid() or info.st_mode & (0o077 if owner_only else 0o022):
                raise ValueError(f"live AutoData {label} has unsafe ownership or mode")
        canary_bytes = self.model_canary_report.read_bytes()
        self.model_canary_sha256 = hashlib.sha256(canary_bytes).hexdigest()
        try:
            profile = json.loads(self.resource_profile_path.read_text())
        except (OSError, ValueError) as exc:
            raise ValueError("live AutoData resource profile is invalid") from exc
        if not isinstance(profile, dict):
            raise ValueError("live AutoData resource profile must be a JSON object")
        self.resource_profile_sha256 = hashlib.sha256(
            _canonical_json(profile)
        ).hexdigest()
        if isinstance(max_wall_seconds, bool) or not isinstance(max_wall_seconds, int):
            raise ValueError("live AutoData max_wall_seconds must be a positive integer")
        if max_wall_seconds < 1:
            raise ValueError("live AutoData max_wall_seconds must be a positive integer")
        self.max_wall_seconds = max_wall_seconds
        values = {
            "driver_script": str(self.driver_script) if self.driver_script.is_file() else "",
            "generator_model": self.generator_model,
            "judge_model": self.judge_model,
            "generator_url": self.generator_url,
            "judge_url": self.judge_url,
            "generator_token_env": self.generator_token_env,
            "judge_token_env": self.judge_token_env,
        }
        missing = sorted(key for key, value in values.items() if not value)
        if missing:
            raise ValueError("live AutoData route is incomplete: " + ", ".join(missing))
        for name in (self.generator_token_env, self.judge_token_env):
            if not os.getenv(name):
                raise ValueError(f"live AutoData credential environment variable is unset: {name}")

    @property
    def models(self) -> Mapping[str, Mapping[str, Any]]:
        generator = {"identity": self.generator_model, "route": self.generator_url}
        if self.generator_deployment_id:
            generator["deployment_id"] = self.generator_deployment_id
        return {
            "generator": generator,
            "judge": {"identity": self.judge_model, "route": self.judge_url},
        }

    @property
    def interactive(self) -> bool:
        return True

    @property
    def resource_evidence_binding(self) -> Mapping[str, str]:
        return {
            "model_canary_sha256": self.model_canary_sha256,
            "resource_profile_sha256": self.resource_profile_sha256,
        }

    def _interactive_operation(
        self,
        operation: str,
        job_root: Path,
        request: Mapping[str, Any],
        ledger: CampaignBudgetLedger,
        *,
        action_id: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        operation_root = job_root / "operations" / (uuid.uuid4().hex)
        operation_root.mkdir(parents=True)
        payload_path = operation_root / "payload.json"
        _write_json(payload_path, dict(payload or {}))
        prepare_path = operation_root / "prepare.json"
        common = [
            self.python,
            str(self.driver_script),
            "--kind",
            operation,
            "--request",
            str(job_root / "request.json"),
            "--state-root",
            str(job_root / "live-state"),
            "--payload",
            str(payload_path),
            "--action-id",
            action_id,
            "--model-canary-report",
            str(self.model_canary_report),
            "--model-canary-sha256",
            self.model_canary_sha256,
            "--resource-profile",
            str(self.resource_profile_path),
            "--resource-profile-sha256",
            self.resource_profile_sha256,
        ]
        prepared = subprocess.run(
            [*common, "--operation", "prepare", "--output", str(prepare_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,
            check=False,
        )
        if prepared.returncode or not prepare_path.is_file():
            detail = prepared.stderr.strip() or "driver omitted preparation plan"
            raise RuntimeError(f"live AutoData prepare failed closed: {detail}")
        plan = json.loads(prepare_path.read_text())
        maximum = Decimal(str(plan.get("maximum_cost_usd", "0")))
        if not maximum.is_finite() or maximum < 0:
            raise RuntimeError("live driver proposed an invalid per-operation cost ceiling")
        if plan.get("performs_model_call") is True and maximum <= 0:
            raise RuntimeError("live driver requested an unreserved model call")
        reservation_id = ""
        scope_id = str(request["controls"]["budget_scope_id"])
        if maximum > 0:
            reservation_id = ledger.reserve(scope_id, maximum)
        result_path = operation_root / "result.json"
        executed = subprocess.run(
            [
                *common,
                "--operation",
                "execute",
                "--output",
                str(result_path),
                "--reservation-id",
                reservation_id,
                "--generator-model",
                self.generator_model,
                "--generator-url",
                self.generator_url,
                "--judge-model",
                self.judge_model,
                "--judge-url",
                self.judge_url,
                "--generator-token-env",
                self.generator_token_env,
                "--judge-token-env",
                self.judge_token_env,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10800,
            check=False,
        )
        result = json.loads(result_path.read_text()) if result_path.is_file() else {}
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        if not reservation_id and any(
            usage.get(key, 0) not in (0, "0")
            for key in ("spent_cost_usd", "model_calls", "input_tokens", "output_tokens")
        ):
            ledger.record_unreserved(
                scope_id,
                actual_cost=usage.get("spent_cost_usd", "0"),
                model_calls=int(usage.get("model_calls", 0)),
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            )
            raise RuntimeError("live driver reported an unreserved model call")
        if reservation_id:
            known_cost = (
                usage.get("spent_cost_usd")
                if usage and result.get("usage_complete") is not False
                else None
            )
            ledger.settle(
                scope_id,
                reservation_id,
                actual_cost=known_cost,
                model_calls=int(usage.get("model_calls", 0)),
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
            )
        if executed.returncode or not result:
            detail = executed.stderr.strip() or "driver omitted operation result"
            raise RuntimeError(f"live AutoData execute failed closed: {detail}")
        return result

    def create_workspace(
        self,
        job_root: Path,
        request: Mapping[str, Any],
        ledger: CampaignBudgetLedger,
    ) -> dict[str, Any]:
        return self._interactive_operation("create_workspace", job_root, request, ledger)

    def step_interactive(
        self,
        job_root: Path,
        request: Mapping[str, Any],
        ledger: CampaignBudgetLedger,
    ) -> dict[str, Any]:
        return self._interactive_operation("step", job_root, request, ledger)

    def action_interactive(
        self,
        operation: str,
        job_root: Path,
        request: Mapping[str, Any],
        action_id: str,
        payload: Mapping[str, Any],
        ledger: CampaignBudgetLedger,
    ) -> dict[str, Any]:
        return self._interactive_operation(
            f"action_{operation}",
            job_root,
            request,
            ledger,
            action_id=action_id,
            payload=payload,
        )

    def run(self, job_root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
        raise RuntimeError(
            "live backend requires interactive workspace/action driving; unattended run is disabled"
        )

class AutoDataJobService:
    """Durable and idempotent registry for asynchronous AutoData jobs."""

    def __init__(
        self,
        state_root: Path,
        pipeline_sha: str,
        *,
        backend: LifecycleBackend,
        required_controls: Mapping[str, Any] | None = None,
        required_spec: Mapping[str, Any] | None = None,
    ) -> None:
        self.state_root = state_root.resolve()
        self.pipeline_sha = pipeline_sha.lower()
        self.backend = backend
        self.required_controls = dict(required_controls or {})
        self.required_spec = dict(required_spec or {})
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.ledger = CampaignBudgetLedger(self.state_root / "budget-scopes")
        self._lock = threading.Lock()

    def _validate_operator_controls(self, controls: Mapping[str, Any]) -> None:
        """Reject direct HTTP attempts to expand the operator-frozen profile."""
        if not self.required_controls:
            return
        for key in (
            "resource_profile",
            "resource_profile_sha256",
            "budget_scope_id",
            "required_retained_rows",
        ):
            if controls.get(key) != self.required_controls.get(key):
                raise ValueError(f"controls.{key} does not match operator policy")
        try:
            requested = Decimal(str(controls.get("max_cost_usd", "")))
            authorized = Decimal(str(self.required_controls.get("max_cost_usd", "")))
        except InvalidOperation as exc:
            raise ValueError("controls.max_cost_usd does not match operator policy") from exc
        if requested != authorized:
            raise ValueError("controls.max_cost_usd does not match operator policy")

    def _validate_scientific_spec(self, spec: Mapping[str, Any]) -> None:
        allowed = {
            "schema",
            "resource_profile",
            "safety_axis",
            "training_mechanism",
            "training_view",
            "seed",
            "goal",
        }
        if set(spec) != allowed:
            raise ValueError("spec does not match the v1 scientific request schema")
        if spec.get("schema") != "aar.autodata.request/v1":
            raise ValueError("spec has an unsupported schema")
        if spec.get("training_view") not in {"sft", "preference"}:
            raise ValueError("spec.training_view is unsupported")
        if isinstance(spec.get("seed"), bool) or not isinstance(spec.get("seed"), int):
            raise ValueError("spec.seed must be an integer")
        limits = {
            "resource_profile": 192,
            "safety_axis": 128,
            "training_mechanism": 512,
            "goal": 2048,
        }
        for key, limit in limits.items():
            value = spec.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"spec.{key} must be a non-empty string")
            if len(value.encode("utf-8")) > limit:
                raise ValueError(f"spec.{key} exceeds the operator limit")
        for key, expected in self.required_spec.items():
            if spec.get(key) != expected:
                raise ValueError(f"spec.{key} does not match operator policy")

    def _root(self, run_id: str) -> Path:
        if not run_id or not all(char.isalnum() or char in "._-" for char in run_id):
            raise ValueError("run_id contains unsupported characters")
        return self.state_root / "runs" / run_id

    def submit(self, request: Mapping[str, Any]) -> dict[str, Any]:
        run_id = str(request.get("run_id", ""))
        if request.get("pipeline_sha") != self.pipeline_sha:
            raise ValueError("pipeline SHA mismatch")
        if not isinstance(request.get("spec"), dict):
            raise ValueError("spec must be an object")
        self._validate_scientific_spec(request["spec"])
        root = self._root(run_id)
        digest = hashlib.sha256(_canonical_json(request)).hexdigest()
        with self._lock:
            if (root / "request.json").is_file():
                saved = json.loads((root / "request.json").read_text())
                if saved["request_sha256"] != digest:
                    raise ValueError("run_id already exists with a different request")
                return self.status(run_id)
        binding = request.get("binding")
        controls = request.get("controls")
        if not isinstance(binding, dict) or not isinstance(controls, dict):
            raise ValueError("binding and controls must be objects")
        self._validate_operator_controls(controls)
        if request["spec"].get("resource_profile") != controls.get("resource_profile"):
            raise ValueError("spec.resource_profile does not match controls.resource_profile")
        expected_spec = hashlib.sha256(_canonical_json(request["spec"])).hexdigest()
        if binding.get("autodata_spec_sha256") != expected_spec:
            raise ValueError("binding autodata_spec_sha256 does not match spec")
        for key in ("idea_name", "method_code_sha256", "autodata_spec_sha256"):
            if not isinstance(binding.get(key), str) or not binding[key]:
                raise ValueError(f"binding.{key} is required")
        profile_digest = str(controls.get("resource_profile_sha256", ""))
        if len(profile_digest) != 64 or any(c not in "0123456789abcdef" for c in profile_digest):
            raise ValueError("controls.resource_profile_sha256 must be a lowercase SHA-256")
        for key in ("resource_profile", "budget_scope_id"):
            if not isinstance(controls.get(key), str) or not controls[key]:
                raise ValueError(f"controls.{key} is required")
        try:
            cost = Decimal(str(controls.get("max_cost_usd", "")))
        except InvalidOperation as exc:
            raise ValueError("controls.max_cost_usd must be a positive decimal") from exc
        if not cost.is_finite() or cost <= 0:
            raise ValueError("controls.max_cost_usd must be a positive decimal")
        retained = controls.get("required_retained_rows")
        if isinstance(retained, bool) or not isinstance(retained, int) or retained < 1:
            raise ValueError("controls.required_retained_rows must be a positive integer")
        self.ledger.register(controls)
        with self._lock:
            root.mkdir(parents=True, exist_ok=False)
            _write_json(root / "request.json", {"request_sha256": digest, "request": request})
            _write_json(
                root / "status.json",
                {
                    "run_id": run_id,
                    "job_id": f"autodata-{digest[:20]}",
                    "state": "created",
                    "phase": "workspace-pending",
                    "drive_mode": "unattended",
                    "pending_action": None,
                },
            )
        if self.backend.interactive:
            try:
                transition = self.backend.create_workspace(
                    root, request, self.ledger
                )
                self._apply_transition(root, request, transition)
            except Exception as exc:
                status = self.status(run_id)
                _write_json(
                    root / "status.json",
                    {
                        **status,
                        "state": "failed",
                        "phase": "workspace-create-failed",
                        "error": str(exc),
                    },
                )
        return self.status(run_id)

    _APPROVAL_KINDS = {"approve_grounding", "approve_baseline", "approve_resources"}

    def _request(self, root: Path) -> dict[str, Any]:
        return json.loads((root / "request.json").read_text())["request"]

    def _approval_result(
        self, root: Path, action: Mapping[str, Any]
    ) -> dict[str, Any]:
        evidence = action.get("evidence")
        if not isinstance(evidence, dict):
            raise RuntimeError("approval action omitted review evidence")
        if evidence.get("schema") != "aar.autodata.approval-evidence/v1":
            raise RuntimeError("approval evidence has an unsupported schema")
        digest = str(evidence.get("artifact_digest", ""))
        digest_hex = digest.removeprefix("sha256:")
        if len(digest_hex) != 64 or any(c not in "0123456789abcdef" for c in digest_hex):
            raise RuntimeError("approval evidence omitted an artifact digest")
        created_sequence = action.get("created_sequence")
        evidence_sequence = evidence.get("recorded_sequence")
        if (
            isinstance(created_sequence, bool)
            or not isinstance(created_sequence, int)
            or isinstance(evidence_sequence, bool)
            or not isinstance(evidence_sequence, int)
            or evidence_sequence >= created_sequence
        ):
            raise RuntimeError("approval evidence was not recorded before the approval action")
        checks = evidence.get("checks")
        if not isinstance(checks, list) or not checks or any(
            not isinstance(check, dict)
            or not isinstance(check.get("name"), str)
            or check.get("passed") is not True
            for check in checks
        ):
            raise RuntimeError("approval evidence checks are missing or did not all pass")
        check_names = {str(check["name"]) for check in checks}
        required_checks = {
            "approve_grounding": {"coverage_present", "provenance_valid"},
            "approve_baseline": {"dry_run_passed", "pipeline_checks_passed"},
            "approve_resources": {
                "resource_profile_verified",
                "budget_scope_verified",
                "startup_model_canary_verified",
                "broker_ready_verified",
                "executor_pins_verified",
            },
        }[str(action["kind"])]
        missing_checks = required_checks - check_names
        if missing_checks:
            raise RuntimeError(
                "approval evidence omitted required checks: "
                + ", ".join(sorted(missing_checks))
            )
        if action["kind"] == "approve_grounding":
            if not isinstance(evidence.get("task_count"), int) or evidence["task_count"] < 1:
                raise RuntimeError("grounding approval evidence has no grounded tasks")
        elif action["kind"] == "approve_baseline":
            if not isinstance(evidence.get("sample_count"), int) or evidence["sample_count"] < 1:
                raise RuntimeError("baseline approval evidence has no tested samples")
        else:
            request = self._request(root)
            controls = request["controls"]
            binding = self.backend.resource_evidence_binding
            if (
                evidence.get("resource_evidence_schema")
                != "aar.autodata.resource-approval-evidence/v1"
                or evidence.get("resource_profile_sha256")
                != controls["resource_profile_sha256"]
                or evidence.get("budget_scope_id") != controls["budget_scope_id"]
                or evidence.get("resource_profile_sha256")
                != binding.get("resource_profile_sha256")
                or evidence.get("model_canary_sha256")
                != binding.get("model_canary_sha256")
                or not isinstance(evidence.get("broker_ready_snapshot_sha256"), str)
                or len(evidence["broker_ready_snapshot_sha256"]) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in evidence["broker_ready_snapshot_sha256"]
                )
                or not isinstance(evidence.get("executor_sha256"), str)
                or len(evidence["executor_sha256"]) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in evidence["executor_sha256"]
                )
            ):
                raise RuntimeError("resource approval evidence does not match operator controls")
        attestation = {
            "schema": "aar.autodata.approval-attestation/v1",
            "principal": "aar-integrity-monitor",
            "action_id": action["id"],
            "action_kind": action["kind"],
            "evidence_digest": digest,
            "evidence_recorded_sequence": evidence_sequence,
            "approval_sequence": created_sequence + 1,
            "approval_policy_sha256": hashlib.sha256(
                b"aar-run8-unattended-production/v1:synthetic-only:no-benchmark-mimicry"
            ).hexdigest(),
        }
        _write_json(root / "approval-attestations" / f"{action['id']}.json", attestation)
        result = {
            "decision": (
                "retry" if action["kind"] == "approve_resources" else "approve"
            ),
            "feedback": "Delegated integrity policy verified all recorded evidence checks.",
            "user_acknowledged": True,
            "approval_attestation": attestation,
        }
        if action["kind"] != "approve_resources":
            result["target"] = (
                "grounding" if action["kind"] == "approve_grounding" else "pipeline"
            )
        return result

    def _apply_transition(
        self,
        root: Path,
        request: Mapping[str, Any],
        transition: Mapping[str, Any],
    ) -> dict[str, Any]:
        status = json.loads((root / "status.json").read_text())
        if transition.get("state") == "complete":
            self._finalize_result(root, request, transition)
            return self.status(str(request["run_id"]))
        action = transition.get("action")
        if action is not None:
            if not isinstance(action, dict) or not action.get("id") or not action.get("kind"):
                raise RuntimeError("live backend returned a malformed host action")
            sequence = int(status.get("sequence", 0)) + 1
            action = dict(action)
            if action.get("kind") in self._APPROVAL_KINDS:
                evidence = action.get("evidence")
                if not isinstance(evidence, dict):
                    raise RuntimeError("approval action omitted review evidence")
                evidence = {**evidence, "recorded_sequence": sequence}
                _write_json(
                    root / "approval-evidence" / f"{action['id']}.json", evidence
                )
                action["evidence"] = evidence
                sequence += 1
            pending = {
                **action,
                "created_sequence": sequence,
                "status": "pending",
            }
            status.update(
                state="waiting_action",
                phase=str(transition.get("phase", action["kind"])),
                pending_action=pending,
                sequence=sequence,
            )
        else:
            status.update(
                state=str(transition.get("state", status.get("state", "running"))),
                phase=str(transition.get("phase", status.get("phase", "running"))),
                pending_action=None,
            )
            for key in ("workspace_id", "study_id", "execution_id", "mode"):
                if key in transition:
                    status[key] = transition[key]
        native_status = transition.get("native_status")
        if native_status is not None:
            if not isinstance(native_status, dict):
                raise RuntimeError("live backend returned malformed native status")
            status["native_status"] = native_status
        _write_json(root / "status.json", status)
        return status

    def _auto_approve(self, root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
        for _ in range(8):
            status = json.loads((root / "status.json").read_text())
            action = status.get("pending_action")
            if not isinstance(action, dict) or action.get("kind") not in self._APPROVAL_KINDS:
                return status
            result = self._approval_result(root, action)
            begun = self.backend.action_interactive(
                "begin",
                root,
                request,
                str(action["id"]),
                {},
                self.ledger,
            )
            lease_token = begun.get("lease_token")
            if not isinstance(lease_token, str) or not lease_token:
                raise RuntimeError("native approval action begin omitted its lease token")
            transition = self.backend.action_interactive(
                "complete",
                root,
                request,
                str(action["id"]),
                {"lease_token": lease_token, "result": result},
                self.ledger,
            )
            status["pending_action"] = None
            status["sequence"] = int(status.get("sequence", 0)) + 1
            _write_json(root / "status.json", status)
            self._apply_transition(root, request, transition)
            status = self.status(str(request["run_id"]))
            if status.get("pending_action") is None:
                return status
        raise RuntimeError("delegated approval loop exceeded its transition limit")

    def _interactive_step_worker(
        self, root: Path, request: Mapping[str, Any]
    ) -> None:
        try:
            transition = self.backend.step_interactive(root, request, self.ledger)
            self._apply_transition(root, request, transition)
            self._auto_approve(root, request)
        except Exception as exc:
            status = json.loads((root / "status.json").read_text())
            _write_json(
                root / "status.json",
                {
                    **status,
                    "state": "failed",
                    "phase": "interactive-step-failed",
                    "operation_running": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
        else:
            status = json.loads((root / "status.json").read_text())
            status["operation_running"] = False
            _write_json(root / "status.json", status)

    def step(self, run_id: str) -> dict[str, Any]:
        """Start unattended driving once; later calls are idempotent status polls."""
        root = self._root(run_id)
        if self.backend.interactive:
            request = self._request(root)
            with self._lock:
                status = self.status(run_id)
                if status.get("state") in {"complete", "failed"}:
                    return status
                if status.get("pending_action") is not None:
                    return status
                if status.get("operation_running") is True:
                    return status
                status.update(
                    state="running",
                    phase="native-step-running",
                    operation_running=True,
                )
                _write_json(root / "status.json", status)
                threading.Thread(
                    target=self._interactive_step_worker,
                    args=(root, request),
                    name=f"{status['job_id']}-step",
                    daemon=True,
                ).start()
                return status
        with self._lock:
            status = self.status(run_id)
            if status["state"] != "created":
                return status
            status.update(state="queued", phase="workspace-create")
            _write_json(root / "status.json", status)
            request = json.loads((root / "request.json").read_text())["request"]
            threading.Thread(
                target=self._run,
                args=(root, request),
                name=str(status["job_id"]),
                daemon=True,
            ).start()
            return status

    def _finalize_result(
        self,
        root: Path,
        request: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError("completed backend result omitted rows")
        controls = request["controls"]
        binding = request["binding"]
        required = int(controls["required_retained_rows"])
        if len(rows) < required:
            raise RuntimeError(f"production retained {len(rows)} rows; required {required}")
        budget = self.ledger.snapshot(str(controls["budget_scope_id"]))
        payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        fields = result.get("manifest_fields", {})
        if not isinstance(fields, dict):
            raise RuntimeError("completed backend result has invalid manifest fields")
        manifest = {
            "schema": "aar.autodata.dataset/v1",
            "run_id": request["run_id"],
            "pipeline_sha": request["pipeline_sha"],
            "row_count": len(rows),
            "dataset_sha256": hashlib.sha256(payload.encode()).hexdigest(),
            "idea_name": binding["idea_name"],
            "method_code_sha256": binding["method_code_sha256"],
            "autodata_spec_sha256": binding["autodata_spec_sha256"],
            "resource_profile": controls["resource_profile"],
            "resource_profile_sha256": controls["resource_profile_sha256"],
            "budget_scope_id": controls["budget_scope_id"],
            "training_view": request["spec"]["training_view"],
            "required_retained_rows": required,
            "counts": fields.pop(
                "counts",
                {"generated": len(rows), "rejected": 0, "retained": len(rows)},
            ),
            "models": {role: dict(value) for role, value in self.backend.models.items()},
            "budget": {
                key: budget[key]
                for key in (
                    "max_cost_usd",
                    "spent_cost_usd",
                    "model_calls",
                    "input_tokens",
                    "output_tokens",
                )
            },
            **fields,
        }
        _write_json(root / "artifacts.json", {"rows": rows, "manifest": manifest})
        status = json.loads((root / "status.json").read_text())
        status.update(
            state="complete",
            phase="complete",
            row_count=len(rows),
            pending_action=None,
            **dict(result.get("status_fields", {})),
        )
        native_status = result.get("native_status")
        if native_status is not None:
            if not isinstance(native_status, dict):
                raise RuntimeError("completed backend result has malformed native status")
            status["native_status"] = native_status
        _write_json(root / "status.json", status)

    def _run(self, root: Path, request: Mapping[str, Any]) -> None:
        status_path = root / "status.json"
        reservation_id = ""
        scope_id = str(request["controls"]["budget_scope_id"])
        try:
            status = json.loads(status_path.read_text())
            _write_json(status_path, {**status, "state": "running", "phase": "native-lifecycle"})
            controls = request["controls"]
            scope_budget = self.ledger.snapshot(scope_id)
            remaining = (
                Decimal(str(scope_budget["max_cost_usd"]))
                - Decimal(str(scope_budget["spent_cost_usd"]))
                - Decimal(str(scope_budget["reserved_cost_usd"]))
            )
            if remaining <= 0:
                raise RuntimeError("shared Autodata model-spend budget is exhausted")
            reservation_id = self.ledger.reserve(scope_id, remaining)
            runtime_request = json.loads(json.dumps(request))
            runtime_request["controls"]["remaining_cost_usd"] = str(remaining)
            result = self.backend.run(root, runtime_request)
            reported_budget = result.get("manifest_fields", {}).pop("budget", {})
            if not isinstance(reported_budget, dict):
                raise RuntimeError("backend returned invalid budget accounting")
            ledger_state = self.ledger.settle(
                scope_id,
                reservation_id,
                actual_cost=reported_budget.get("spent_cost_usd", "0"),
                model_calls=int(reported_budget.get("model_calls", 0)),
                input_tokens=int(reported_budget.get("input_tokens", 0)),
                output_tokens=int(reported_budget.get("output_tokens", 0)),
            )
            reservation_id = ""
            rows = result["rows"]
            spec = request["spec"]
            binding = request["binding"]
            required = int(controls["required_retained_rows"])
            if required < 1 or len(rows) < required:
                raise RuntimeError(f"production retained {len(rows)} rows; required {required}")
            payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
            manifest = {
                "schema": "aar.autodata.dataset/v1",
                "run_id": request["run_id"],
                "pipeline_sha": request["pipeline_sha"],
                "row_count": len(rows),
                "dataset_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                "idea_name": binding["idea_name"],
                "method_code_sha256": binding["method_code_sha256"],
                "autodata_spec_sha256": binding["autodata_spec_sha256"],
                "resource_profile": controls["resource_profile"],
                "resource_profile_sha256": controls["resource_profile_sha256"],
                "budget_scope_id": controls["budget_scope_id"],
                "training_view": str(spec.get("training_view", "sft")),
                "required_retained_rows": required,
                "counts": {"generated": len(rows), "rejected": 0, "retained": len(rows)},
                "models": {role: dict(value) for role, value in self.backend.models.items()},
                "budget": {
                    "max_cost_usd": controls["max_cost_usd"],
                    "spent_cost_usd": reported_budget.get("spent_cost_usd", "0"),
                    "model_calls": int(reported_budget.get("model_calls", 0)),
                    "input_tokens": int(reported_budget.get("input_tokens", 0)),
                    "output_tokens": int(reported_budget.get("output_tokens", 0)),
                    "scope_spent_cost_usd": ledger_state["spent_cost_usd"],
                    "scope_remaining_cost_usd": str(
                        Decimal(str(ledger_state["max_cost_usd"]))
                        - Decimal(str(ledger_state["spent_cost_usd"]))
                    ),
                },
                **result["manifest_fields"],
            }
            _write_json(root / "artifacts.json", {"rows": rows, "manifest": manifest})
            status = json.loads(status_path.read_text())
            _write_json(
                status_path,
                {
                    **status,
                    "state": "complete",
                    "phase": "complete",
                    "row_count": len(rows),
                    **result["status_fields"],
                },
            )
        except Exception as exc:
            if reservation_id:
                try:
                    self.ledger.settle(
                        scope_id,
                        reservation_id,
                        actual_cost=None,
                        model_calls=0,
                        input_tokens=0,
                        output_tokens=0,
                    )
                except Exception:
                    pass
            status = json.loads(status_path.read_text()) if status_path.is_file() else {}
            _write_json(
                status_path,
                {
                    **status,
                    "state": "failed",
                    "phase": "failed",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )

    def status(self, run_id: str) -> dict[str, Any]:
        path = self._root(run_id) / "status.json"
        if not path.is_file():
            raise FileNotFoundError(run_id)
        return json.loads(path.read_text())

    def artifacts(self, run_id: str) -> dict[str, Any]:
        status = self.status(run_id)
        if status.get("state") != "complete":
            raise RuntimeError(f"job is not complete (state={status.get('state')})")
        return {
            "run_id": run_id,
            **json.loads((self._root(run_id) / "artifacts.json").read_text()),
        }

    def lease_action(self, run_id: str, action_id: str) -> dict[str, Any]:
        status = self.status(run_id)
        pending = status.get("pending_action")
        if not isinstance(pending, dict) or pending.get("id") != action_id:
            raise RuntimeError("no matching host action is pending")
        if pending.get("kind") in {
            "approve_grounding",
            "approve_baseline",
            "approve_resources",
        }:
            raise RuntimeError("approval actions are reserved for the integrity monitor")
        existing_token = pending.get("lease_token")
        if pending.get("status") == "leased":
            if not isinstance(existing_token, str) or not existing_token:
                raise RuntimeError("leased action omitted its native lease token")
            return {
                "run_id": run_id,
                "action": pending,
                "lease_token": existing_token,
            }
        if self.backend.interactive:
            root = self._root(run_id)
            request = self._request(root)
            begun = self.backend.action_interactive(
                "begin", root, request, action_id, {}, self.ledger
            )
            token = begun.get("lease_token")
            if not isinstance(token, str) or not token:
                raise RuntimeError("native action begin omitted its lease token")
        else:
            # The deterministic test backend has no native action store.
            token = uuid.uuid4().hex
        # Mirror the native token only to bind the follow-up HTTP request; the
        # adapter does not mint or independently advance an action lease.
        pending = {**pending, "lease_token": token, "status": "leased"}
        _write_json(
            self._root(run_id) / "status.json",
            {**status, "pending_action": pending},
        )
        return {"run_id": run_id, "action": pending, "lease_token": token}

    def complete_action(
        self, run_id: str, action_id: str, lease_token: str, result: Mapping[str, Any]
    ) -> dict[str, Any]:
        status = self.status(run_id)
        pending = status.get("pending_action")
        if not isinstance(pending, dict) or pending.get("id") != action_id:
            raise RuntimeError("no matching host action is pending")
        if pending.get("lease_token") != lease_token:
            raise RuntimeError("action lease token mismatch")
        if pending.get("kind") in self._APPROVAL_KINDS:
            raise RuntimeError("approval actions are reserved for the integrity monitor")
        record = {"action_id": action_id, "result": dict(result)}
        _write_json(self._root(run_id) / "completed-actions" / f"{action_id}.json", record)
        if self.backend.interactive:
            root = self._root(run_id)
            request = self._request(root)
            transition = self.backend.action_interactive(
                "complete",
                root,
                request,
                action_id,
                {"lease_token": lease_token, "result": dict(result)},
                self.ledger,
            )
            status["pending_action"] = None
            status["sequence"] = int(status.get("sequence", 0)) + 1
            _write_json(root / "status.json", status)
            self._apply_transition(root, request, transition)
            response = self._auto_approve(root, request)
            return {"run_id": run_id, "action_id": action_id, "status": "completed", **response}
        status["pending_action"] = None
        _write_json(self._root(run_id) / "status.json", status)
        return {"run_id": run_id, "action_id": action_id, "status": "completed"}

    def fail_action(
        self, run_id: str, action_id: str, lease_token: str, reason: str
    ) -> dict[str, Any]:
        status = self.status(run_id)
        pending = status.get("pending_action")
        if not isinstance(pending, dict) or pending.get("id") != action_id:
            raise RuntimeError("no matching host action is pending")
        if pending.get("lease_token") != lease_token:
            raise RuntimeError("action lease token mismatch")
        if not reason.strip():
            raise ValueError("action failure reason is required")
        record = {"action_id": action_id, "reason": reason}
        _write_json(self._root(run_id) / "failed-actions" / f"{action_id}.json", record)
        if self.backend.interactive:
            root = self._root(run_id)
            request = self._request(root)
            transition = self.backend.action_interactive(
                "fail",
                root,
                request,
                action_id,
                {"lease_token": lease_token, "reason": reason},
                self.ledger,
            )
            status["pending_action"] = None
            status["sequence"] = int(status.get("sequence", 0)) + 1
            _write_json(root / "status.json", status)
            response = self._apply_transition(root, request, transition)
            return {"run_id": run_id, "action_id": action_id, "status": "failed", **response}
        status["pending_action"] = None
        _write_json(self._root(run_id) / "status.json", status)
        return {"run_id": run_id, "action_id": action_id, "status": "failed"}


def make_handler(
    service: AutoDataJobService, bearer_token: str = ""
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AARAutoDataService/1"

        def _send(self, status: int, value: Mapping[str, Any]) -> None:
            body = json.dumps(dict(value), sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            value = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            if not isinstance(value, dict):
                raise ValueError("request body must be an object")
            return value

        def _authorized(self) -> bool:
            return not bearer_token or self.headers.get("Authorization") == f"Bearer {bearer_token}"

        def do_POST(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            parts = [part for part in urlparse(self.path).path.split("/") if part]
            try:
                if parts == ["v1", "jobs"]:
                    self._send(HTTPStatus.ACCEPTED, service.submit(self._body()))
                    return
                if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "step":
                    self._send(HTTPStatus.OK, service.step(parts[2]))
                    return
                if len(parts) == 6 and parts[:2] == ["v1", "runs"] and parts[3] == "actions":
                    if parts[5] == "begin":
                        self._send(HTTPStatus.OK, service.lease_action(parts[2], parts[4]))
                        return
                    if parts[5] == "complete":
                        body = self._body()
                        self._send(
                            HTTPStatus.OK,
                            service.complete_action(
                                parts[2],
                                parts[4],
                                str(body.get("lease_token", "")),
                                body.get("result", {}),
                            ),
                        )
                        return
                    if parts[5] == "fail":
                        body = self._body()
                        self._send(
                            HTTPStatus.OK,
                            service.fail_action(
                                parts[2],
                                parts[4],
                                str(body.get("lease_token", "")),
                                str(body.get("reason", "")),
                            ),
                        )
                        return
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
            except FileNotFoundError:
                self._send(HTTPStatus.NOT_FOUND, {"error": "run not found"})
            except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
                self._send(HTTPStatus.CONFLICT, {"error": str(exc)})

        def do_GET(self) -> None:  # noqa: N802
            if not self._authorized():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            path = urlparse(self.path).path
            if path == "/health":
                self._send(HTTPStatus.OK, {"status": "ok", "pipeline_sha": service.pipeline_sha})
                return
            parts = [part for part in path.split("/") if part]
            if len(parts) not in (3, 4) or parts[:2] != ["v1", "runs"]:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                if len(parts) == 3:
                    value = service.status(parts[2])
                elif parts[3] == "artifacts":
                    value = service.artifacts(parts[2])
                else:
                    self._send(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                self._send(HTTPStatus.OK, value)
            except FileNotFoundError:
                self._send(HTTPStatus.NOT_FOUND, {"error": "run not found"})
            except RuntimeError as exc:
                self._send(HTTPStatus.CONFLICT, {"error": str(exc)})

        def log_message(self, fmt: str, *args: object) -> None:
            print(f"[aar-autodata-service] {self.address_string()} {fmt % args}", flush=True)

    return Handler


def serve(
    service: AutoDataJobService,
    *,
    host: str = "127.0.0.1",
    port: int = 8792,
    bearer_token: str = "",
) -> None:
    ThreadingHTTPServer((host, port), make_handler(service, bearer_token)).serve_forever()
