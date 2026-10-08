#!/usr/bin/env python3
"""Small real native AutoData meta -> winner -> production canary.

The script is an operator-owned test driver, not an alternate lifecycle. Every
state transition goes through the pinned plugin's original native CLI. It uses
the AAR approval monitor only for the two signed workspace approval actions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RECIPE = (
    REPO / "aar" / "autodata_recipes" / "dishonest_sycophancy_concealing"
)
IMAGE = "docker.io/library/python@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f"
IMAGE_ID = "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--recipe-root", type=Path, default=DEFAULT_RECIPE)
    parser.add_argument("--broker-url", default="http://127.0.0.1:8791")
    parser.add_argument("--broker-auth-token-file", type=Path, required=True)
    parser.add_argument("--model-api-env-file", type=Path, required=True)
    parser.add_argument("--task-count", type=int, default=4)
    parser.add_argument("--required-rows", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--max-cost-usd", type=Decimal, default=Decimal("1.00"))
    parser.add_argument("--timeout-seconds", type=int, default=7200)
    return parser.parse_args()


def _secret(path: Path, *, assignment: str | None = None) -> str:
    path = path.expanduser().resolve(strict=True)
    info = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise RuntimeError(f"secret file must be a mode-0600 regular file: {path}")
    value = path.read_text(encoding="utf-8").strip()
    if assignment and value.startswith(f"{assignment}="):
        value = value.split("=", 1)[1].strip().strip("'\"")
    elif assignment and value.startswith(f"export {assignment}="):
        value = value.split("=", 1)[1].strip().strip("'\"")
    if not value or any(character.isspace() for character in value):
        raise RuntimeError(f"secret file contains no safe {assignment or 'token'} value")
    return value


class Driver:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.root = args.root.expanduser().resolve()
        if self.root.exists() and any(self.root.iterdir()):
            raise RuntimeError("--root must be absent or empty")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.plugin = args.plugin_root.expanduser().resolve(strict=True)
        self.recipe = args.recipe_root.expanduser().resolve(strict=True)
        self.wrapper = self.plugin / "scripts" / "autodata.py"
        if not self.wrapper.is_file():
            raise RuntimeError("pinned AutoData plugin wrapper is missing")
        if args.task_count < 4:
            raise RuntimeError("small meta canary requires at least four tasks")
        if args.required_rows < 1 or args.required_rows > args.task_count:
            raise RuntimeError("required rows must be in [1, task-count]")
        if args.concurrency < 1 or args.concurrency > 64:
            raise RuntimeError("concurrency must be in [1,64]")
        self.state = self.root / "native" / "state.db"
        self.artifacts = self.root / "native" / "artifacts"
        self.workspaces = self.root / "native" / "workspaces"
        self.draft = self.root / "draft"
        self.input = self.root / "input"
        self.approvals = self.root / "approvals"
        self.export = self.root / "export"
        self.secrets = self.root / "secrets"
        for path in (
            self.state.parent,
            self.artifacts,
            self.workspaces,
            self.draft,
            self.input,
            self.approvals,
            self.export,
            self.secrets,
        ):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.progress = self.root / "progress.jsonl"
        self.environment = os.environ.copy()
        self.environment["AUTODATA_BROKER_AUTH_TOKEN"] = _secret(
            args.broker_auth_token_file
        )
        self.environment["MODEL_API_KEY"] = _secret(
            args.model_api_env_file, assignment="MODEL_API_KEY"
        )
        self.started = time.monotonic()

    def milestone(self, name: str, **fields: Any) -> None:
        value = {
            "schema": "aar.autodata.real-e2e-progress/v1",
            "milestone": name,
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
            **fields,
        }
        with self.progress.open("a", encoding="utf-8") as output:
            output.write(json.dumps(value, sort_keys=True) + "\n")
        print(f"[autodata-e2e] {name}", flush=True)

    def cli(self, *arguments: str, timeout: int | None = None) -> dict[str, Any]:
        command = [
            sys.executable,
            str(self.wrapper),
            "--state",
            str(self.state),
            "--artifacts",
            str(self.artifacts),
            "--workspaces",
            str(self.workspaces),
            *arguments,
        ]
        for attempt in range(1, 4):
            completed = subprocess.run(
                command,
                cwd=self.root,
                env=self.environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout or self.args.timeout_seconds,
                check=False,
            )
            if completed.returncode == 0:
                break
            if (
                "could not reach AutoData broker" not in completed.stderr
                or attempt == 3
            ):
                break
            self.milestone(
                "broker_command_retry",
                command=" ".join(arguments[:3]),
                attempt=attempt + 1,
            )
            time.sleep(float(attempt))
        if completed.returncode != 0:
            raise RuntimeError(
                "native AutoData command failed for "
                + " ".join(arguments[:3])
                + ": "
                + completed.stderr[-2000:]
            )
        value = json.loads(completed.stdout)
        if not isinstance(value, dict):
            raise RuntimeError("native AutoData command returned non-object JSON")
        return value

    def complete(self, action: dict[str, Any], result: dict[str, Any]) -> None:
        begun = self.cli("action", "begin", str(action["id"]))
        path = self.root / f".{action['id']}.result.json"
        path.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
        try:
            self.cli(
                "action",
                "complete",
                str(action["id"]),
                "--lease-token",
                str(begun["lease_token"]),
                "--result",
                str(path),
            )
        finally:
            path.unlink(missing_ok=True)

    def _generate_approval_keys(self) -> tuple[Path, Path, str]:
        private = self.secrets / "approval-private.pem"
        public = self.draft / "approval" / "public.pem"
        public.parent.mkdir(parents=True)
        subprocess.run(
            [
                "openssl",
                "genpkey",
                "-algorithm",
                "RSA",
                "-pkeyopt",
                "rsa_keygen_bits:3072",
                "-out",
                str(private),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        private.chmod(0o600)
        subprocess.run(
            [
                "openssl",
                "pkey",
                "-in",
                str(private),
                "-pubout",
                "-out",
                str(public),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return private, public, "sha256:" + hashlib.sha256(public.read_bytes()).hexdigest()

    def executor(self) -> dict[str, Any]:
        return {
            "kind": "sandoq-firecracker",
            "environment": "oci-runner-firecracker-small",
            "image": IMAGE,
            "expected_image_id": IMAGE_ID,
            "broker_url": self.args.broker_url,
            "broker_auth_secret_ref": "AUTODATA_BROKER_AUTH_TOKEN",
            "model_backed": True,
            "cpus": 2,
            "memory_mb": 2048,
            "network": "host",
            "workdir": "/workspace",
            "non_secret_env": {
                "AUTODATA_GENERATOR_URL": "https://ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud/v1",
                "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
                "AUTODATA_GENERATOR_DEPLOYMENT_ID": "winnieyangwn-kimi26",
                "AUTODATA_GENERATOR_MAX_INPUT": "4096",
                "AUTODATA_GENERATOR_MAX_OUTPUT": "768",
                "AUTODATA_GENERATOR_TIMEOUT": "90",
                "AUTODATA_GENERATOR_INPUT_USD_PER_MILLION": "1",
                "AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION": "4",
                "AUTODATA_JUDGE_URL": "https://api.meta.ai/v1/responses",
                "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
                "AUTODATA_JUDGE_MAX_INPUT": "4096",
                "AUTODATA_JUDGE_MAX_OUTPUT": "512",
                "AUTODATA_JUDGE_TIMEOUT": "90",
                "AUTODATA_JUDGE_INPUT_USD_PER_MILLION": "1",
                "AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION": "4",
                "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS": "1",
            },
        }

    def _preflight_budget(self) -> None:
        per_task = (
            Decimal(4096 + 4096) * Decimal(1)
            + Decimal(768 + 512) * Decimal(4)
        ) / Decimal(1_000_000)
        # Authoring dry run + meta phases/check with replenishment headroom +
        # fixed production. A one-iteration meta run executes tuning evidence,
        # paired parent/candidate evidence, hidden selection, post-mutation
        # tuning, the final corpus, and one checker attempt.
        meta_attempts = 1 + 4 * self.args.task_count
        authorized_attempts = (
            self.args.task_count
            + meta_attempts
            + self.args.task_count
        )
        maximum = per_task * authorized_attempts
        if maximum > self.args.max_cost_usd:
            raise RuntimeError(
                f"worst-case model task cost {maximum} exceeds cap {self.args.max_cost_usd}"
            )
        self.milestone(
            "budget_preflight_passed",
            max_cost_usd=str(self.args.max_cost_usd),
            worst_case_task_cost_usd=str(maximum),
            authorized_task_attempts=authorized_attempts,
        )

    def _prepare_brief(self) -> tuple[Path, Path]:
        private, _, public_digest = self._generate_approval_keys()
        brief = json.loads((self.recipe / "autodata.workspace.json").read_text())
        executor = self.executor()
        brief["authoring_executor"] = executor
        brief["authoring_budget"] = {
            "max_iterations": 8,
            "max_task_attempts": self.args.task_count,
            "max_wall_seconds": self.args.timeout_seconds,
        }
        brief["execution_defaults"] = {
            "mode": "meta_optimize",
            "split_seed": 20261008,
            "executor": executor,
            "budget": {
                "max_iterations": 1,
                "max_task_attempts": 20,
                "max_wall_seconds": self.args.timeout_seconds,
            },
            "concurrency": self.args.concurrency,
            "secret_references": ["AUTODATA_BROKER_AUTH_TOKEN"],
        }
        brief["approval_policy"] = {
            "mode": "delegated",
            "public_key_path": "approval/public.pem",
            "public_key_sha256": public_digest,
            "actor": "aar-integrity-monitor",
            "policy_version": "aar-autodata/run9-v1",
        }
        path = self.draft / "autodata.workspace.json"
        path.write_text(json.dumps(brief, sort_keys=True, indent=2) + "\n")
        return path, private

    def _stage_grounding(self) -> None:
        shutil.copytree(self.recipe / "grounding", self.draft / "grounding")
        coverage_path = self.draft / "grounding" / "coverage.json"
        coverage = json.loads(coverage_path.read_text())
        coverage["minimum_task_count"] = self.args.task_count
        coverage_path.write_text(json.dumps(coverage, sort_keys=True, indent=2) + "\n")
        subprocess.run(
            [
                sys.executable,
                str(self.draft / "grounding" / "build_manifest.py"),
                "--count",
                str(self.args.task_count),
                "--coverage",
                str(coverage_path),
                "--output",
                str(self.draft / "grounding" / "manifest.json"),
            ],
            check=True,
        )

    def _stage_pipeline(self) -> None:
        for name in (
            "autodata.pipeline.json",
            "framework.lock.json",
            "objective.json",
            "comparator.json",
        ):
            shutil.copy2(self.recipe / name, self.draft / name)
        shutil.copytree(self.recipe / "recipe", self.draft / "recipe")
        shutil.copytree(self.recipe / "schemas", self.draft / "schemas")

    def _configure_approval(self, private_key: Path) -> None:
        settings = {
            "AAR_AUTODATA_PLUGIN_ROOT": str(self.plugin),
            "AAR_AUTODATA_STATE": str(self.state),
            "AAR_AUTODATA_ARTIFACTS": str(self.artifacts),
            "AAR_AUTODATA_WORKSPACES": str(self.workspaces),
            "AAR_AUTODATA_APPROVAL_PRIVATE_KEY": str(private_key),
            "AAR_AUTODATA_APPROVAL_AUDIT_DIR": str(self.approvals),
            "AAR_AUTODATA_APPROVAL_ACTOR": "aar-integrity-monitor",
            "AAR_AUTODATA_APPROVAL_POLICY_VERSION": "aar-autodata/run9-v1",
            "AAR_MONITOR_BACKEND": "model_api",
            "MONITOR_MODEL": "gpt-5-6-luna",
            "MODEL_API_KEY": self.environment["MODEL_API_KEY"],
            "AUTODATA_BROKER_AUTH_TOKEN": self.environment["AUTODATA_BROKER_AUTH_TOKEN"],
        }
        os.environ.update(settings)

    def _review(self, action: dict[str, Any]) -> None:
        from aar.research_loop.autodata_approval import review_and_complete_action

        audit = review_and_complete_action(str(action["id"]))
        if audit.get("decision") not in {"approve", "retry"}:
            raise RuntimeError(
                f"delegated monitor requested revision: {audit.get('feedback')}"
            )
        self.milestone(
            f"{action['kind']}_signed",
            action_id=action["id"],
            payload_sha256=audit["payload_sha256"],
        )

    def _workspace(self, brief: Path, private_key: Path) -> tuple[str, str, Path]:
        created = self.cli(
            "workspace", "create", "--brief", str(brief), "--root", str(self.draft)
        )
        workspace_id = str(created["workspace_id"])
        self._configure_approval(private_key)
        action = self.cli("workspace", "step", workspace_id)
        self.complete(action, {"summary": "Operator brief confirmed", "decisions": []})
        action = self.cli("workspace", "step", workspace_id)
        self._stage_grounding()
        self.complete(
            action,
            {
                "summary": f"Staged {self.args.task_count} synthetic covered tasks",
                "decisions": ["No external or evaluation sources"],
            },
        )
        action = self.cli("workspace", "step", workspace_id)
        self._review(action)
        action = self.cli("workspace", "step", workspace_id)
        self._stage_pipeline()
        self.complete(
            action,
            {
                "summary": "Staged Kimi generation and independent Luna judgment",
                "decisions": ["Only generation_strategy.json is mutable"],
            },
        )
        action = self.cli("workspace", "step", workspace_id)
        self._review(action)
        frozen = self.cli("workspace", "step", workspace_id)
        if frozen.get("status") != "frozen":
            raise RuntimeError("native workspace did not freeze")
        snapshot = self.export / "frozen-workspace"
        self.cli("workspace", "export", workspace_id, "--output", str(snapshot))
        self.milestone(
            "workspace_frozen",
            workspace_id=workspace_id,
            default_execution_id=frozen["execution_id"],
        )
        return workspace_id, str(frozen["execution_id"]), snapshot

    def _execution_spec(
        self,
        root: Path,
        *,
        mode: str,
        tuning: list[str] | None = None,
        validation: list[str] | None = None,
    ) -> Path:
        manifest = root / "grounding" / "manifest.json"
        digest = "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest()
        value: dict[str, Any] = {
            "schema": "autodata.execution/v1",
            "grounding": {"manifest_path": "grounding/manifest.json", "digest": digest},
            "mode": mode,
            "split_seed": 20261008,
            "executor": self.executor(),
            "budget": {
                "max_iterations": 1 if mode == "meta_optimize" else 0,
                "max_task_attempts": (
                    1 + 4 * self.args.task_count
                    if mode == "meta_optimize"
                    else self.args.task_count
                ),
                "max_wall_seconds": self.args.timeout_seconds,
            },
            "concurrency": self.args.concurrency,
            "secret_references": ["AUTODATA_BROKER_AUTH_TOKEN"],
        }
        if mode == "meta_optimize":
            value["tuning_task_ids"] = tuning
            value["validation_task_ids"] = validation
        path = self.input / f"{mode}.execution.json"
        path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
        return path

    def _create_execution(self, pipeline_root: Path, spec: Path, key: str) -> str:
        created = self.cli(
            "execution",
            "create",
            "--pipeline",
            str(pipeline_root / "autodata.pipeline.json"),
            "--execution",
            str(spec),
            "--idempotency-key",
            key,
        )
        return str(created["execution_id"])

    def _run_meta(self, snapshot: Path) -> tuple[str, Path]:
        grounding = json.loads((snapshot / "grounding" / "manifest.json").read_text())
        ids = [str(task["id"]) for task in grounding["tasks"]]
        midpoint = len(ids) // 2
        spec = self._execution_spec(
            snapshot,
            mode="meta_optimize",
            tuning=ids[:midpoint],
            validation=ids[midpoint:],
        )
        execution_id = self._create_execution(snapshot, spec, "run9-real-meta-v1")
        analysis = self.cli("execution", "step", execution_id)
        self.complete(
            analysis,
            {
                "proposal": "Reduce sampling temperature from 0.2 to 0.1 to improve consistency while preserving scenario diversity.",
                "dashboard_summary": "Test a single bounded sampling change.",
            },
        )
        mutation = self.cli("execution", "step", execution_id)
        begun = self.cli("action", "begin", str(mutation["id"]))
        strategy_path = Path(str(mutation["editable_root"])) / "recipe" / "generation_strategy.json"
        strategy = json.loads(strategy_path.read_text())
        strategy["name"] = "truthful-calibrated-temperature-01-v1"
        strategy["temperature"] = 0.1
        strategy_path.write_text(json.dumps(strategy, sort_keys=True, indent=2) + "\n")
        result_path = self.root / ".meta-mutation.json"
        result_path.write_text(json.dumps({"summary": "Reduced temperature to 0.1"}))
        try:
            self.cli(
                "action",
                "complete",
                str(mutation["id"]),
                "--lease-token",
                str(begun["lease_token"]),
                "--result",
                str(result_path),
            )
        finally:
            result_path.unlink(missing_ok=True)
        completed = self.cli("execution", "step", execution_id)
        if completed.get("status") != "completed":
            raise RuntimeError("meta-optimization did not complete")
        winner = self.export / "meta-winner"
        exported = self.cli(
            "execution", "export-winner", execution_id, "--output", str(winner)
        )
        self.milestone(
            "meta_completed",
            execution_id=execution_id,
            winner_candidate_id=exported["winner_candidate_id"],
            winner_tree_digest=exported["winner_tree_digest"],
            tuning_count=len(ids[:midpoint]),
            validation_count=len(ids[midpoint:]),
        )
        return execution_id, winner

    def _run_production(self, winner: Path) -> tuple[str, Path, int]:
        spec = self._execution_spec(winner, mode="production")
        execution_id = self._create_execution(winner, spec, "run9-real-production-v1")
        completed = self.cli("execution", "step", execution_id)
        if completed.get("status") != "completed":
            raise RuntimeError("fixed-winner production did not complete")
        dataset = self.export / "production-dataset.json"
        self.cli("export", execution_id, "--output", str(dataset))
        from aar.infrastructure.autodata_dataset import load_autodata_dataset

        rows = load_autodata_dataset(
            dataset,
            receipt_path=self.export / "training-consumption.json",
            required_rows=self.args.required_rows,
            expected_execution_id=execution_id,
        )
        self.milestone(
            "production_consumed",
            execution_id=execution_id,
            accepted_rows=len(rows),
            dataset_sha256="sha256:" + hashlib.sha256(dataset.read_bytes()).hexdigest(),
        )
        return execution_id, dataset, len(rows)

    def run(self) -> dict[str, Any]:
        self._preflight_budget()
        brief, private = self._prepare_brief()
        workspace_id, default_execution_id, snapshot = self._workspace(brief, private)
        meta_execution_id, winner = self._run_meta(snapshot)
        production_execution_id, dataset, accepted = self._run_production(winner)
        report = {
            "schema": "aar.autodata.native-real-e2e/v1",
            "status": "passed",
            "workspace_id": workspace_id,
            "unused_default_execution_id": default_execution_id,
            "meta_execution_id": meta_execution_id,
            "production_execution_id": production_execution_id,
            "task_count": self.args.task_count,
            "required_rows": self.args.required_rows,
            "concurrency": self.args.concurrency,
            "accepted_rows": accepted,
            "dataset": str(dataset),
            "dataset_sha256": "sha256:" + hashlib.sha256(dataset.read_bytes()).hexdigest(),
            "approval_audits": sorted(path.name for path in self.approvals.glob("*.json")),
            "elapsed_seconds": round(time.monotonic() - self.started, 3),
        }
        report_path = self.root / "report.json"
        report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        report_path.chmod(0o600)
        self.milestone("e2e_passed", report=str(report_path))
        return report


def main() -> int:
    args = _args()
    report = Driver(args).run()
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
