"""Bounded, durable recovery for terminal multi-chain AAR controllers."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from aar.slurm_session_recovery import classify_state, reconcile_session_result


STATE_SCHEMA = "aar.controller-supervisor/v1"
EVENT_SCHEMA = "aar.controller-supervisor-event/v1"


@dataclass(frozen=True)
class JobStatus:
    state: str
    exit_code: str


@dataclass(frozen=True)
class ChainSnapshot:
    seed: str
    controller_job: str
    evaluator_job: str
    pairs: int
    sessions: int
    active_training_jobs: tuple[str, ...]
    unscored_claims: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryDecision:
    action: str
    reason: str


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _safe_job(value: str) -> str:
    if not value.isdigit():
        raise ValueError(f"invalid Slurm job ID: {value!r}")
    return value


def read_latest_jobs(
    attempt: Path, seeds: Iterable[str]
) -> tuple[dict[str, str], dict[str, str]]:
    allowed = set(seeds)
    controllers: dict[str, str] = {}
    evaluators: dict[str, str] = {}
    children = attempt / "metadata" / "children.tsv"
    for raw in children.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        if len(fields) != 3 or fields[0] not in allowed:
            continue
        seed, evaluator, controller = fields
        controllers[seed] = _safe_job(controller)
        evaluators[seed] = _safe_job(evaluator)

    registry = attempt / "metadata" / "recovery_jobs.tsv"
    if registry.is_file():
        for raw in registry.read_text(encoding="utf-8").splitlines():
            fields = raw.split("\t")
            if len(fields) < 4:
                continue
            _timestamp, kind, seed, job = fields[:4]
            if seed not in allowed or not job.isdigit():
                continue
            if kind == "chain":
                controllers[seed] = job
            elif kind in {"evaluator", "evaluator_reused"}:
                evaluators[seed] = job

    missing = allowed - controllers.keys()
    if missing:
        raise RuntimeError(
            "missing controller job for chain(s): " + ", ".join(sorted(missing))
        )
    missing = allowed - evaluators.keys()
    if missing:
        raise RuntimeError(
            "missing evaluator job for chain(s): " + ", ".join(sorted(missing))
        )
    return controllers, evaluators


def team_for_seed(attempt: Path, seed: str) -> Path:
    launch_job = ""
    for line in (attempt / "metadata" / "submission.txt").read_text(
        encoding="utf-8"
    ).splitlines():
        if line.startswith("launch_job_id="):
            launch_job = line.removeprefix("launch_job_id=")
            break
    _safe_job(launch_job)
    team = (
        attempt
        / "aar_teams"
        / f"run15-gemma4-31b-kimi26-{seed}-{launch_job}"
    )
    if not team.is_dir():
        raise RuntimeError(f"missing team directory for {seed}: {team}")
    return team


def count_sessions(team: Path, seed: str) -> int:
    return sum(1 for _ in (team / "logs").glob(f"session_*_{seed}_*.log"))


def count_pairs(team: Path) -> int:
    scores: set[str] = set()
    for path in (team / "scores").glob("*.json"):
        if path.name.endswith(".failed.json"):
            continue
        value = _read_json(path)
        if value is None:
            continue
        run_id = value.get("run_id")
        if isinstance(run_id, str) and run_id:
            scores.add(run_id)
        else:
            scores.add(path.stem)

    findings: set[str] = set()
    for path in (team / ".finding_dedup").glob("runid_*/post.json"):
        value = _read_json(path)
        if value is not None and isinstance(value.get("run_id"), str):
            findings.add(str(value["run_id"]))
    return len(scores & findings)


def active_training_jobs(
    team: Path, status_for: Callable[[str], JobStatus]
) -> tuple[str, ...]:
    active: list[str] = []
    for receipt in (team / ".train_submissions").glob("*.env"):
        job = ""
        for line in receipt.read_text(encoding="utf-8").splitlines():
            if line.startswith("job_id="):
                job = line.removeprefix("job_id=")
                break
        if not job.isdigit():
            continue
        if not classify_state(status_for(job).state).terminal:
            active.append(job)
    return tuple(sorted(set(active), key=int))


def unscored_claims(team: Path) -> tuple[str, ...]:
    pending: list[str] = []
    for claim in (team / "scores" / ".claims").iterdir():
        if not claim.is_dir():
            continue
        run_id = claim.name
        if not (team / "scores" / f"{run_id}.json").is_file() and not (
            team / "scores" / f"{run_id}.failed.json"
        ).is_file():
            pending.append(run_id)
    return tuple(sorted(pending))


def receipt_disposition(team: Path, controller_job: str) -> str | None:
    value = _read_json(
        team / "logs" / f"research-session-result-{controller_job}.json"
    )
    if value is None:
        return None
    if value.get("schema") == "aar.research-session-result/v2":
        nested = value.get("process_result")
        value = nested if isinstance(nested, dict) else {}
    if str(value.get("job_id") or controller_job) != controller_job:
        return None
    disposition = value.get("recovery_disposition")
    return disposition if disposition in {"complete", "recover", "halt"} else None


def decide_recovery(
    snapshot: ChainSnapshot,
    controller_status: JobStatus,
    evaluator_status: JobStatus,
    *,
    receipt: str | None,
    target_pairs: int,
    session_ceiling: int,
    restart_count: int,
    max_restarts: int,
) -> RecoveryDecision:
    if snapshot.pairs >= target_pairs:
        return RecoveryDecision("complete", "target_pairs_reached")
    if snapshot.sessions >= session_ceiling:
        return RecoveryDecision("halt", "session_ceiling_exhausted")

    terminal = classify_state(controller_status.state)
    if not terminal.terminal:
        return RecoveryDecision("watch", "controller_active")
    if restart_count >= max_restarts:
        return RecoveryDecision("halt", "controller_restart_limit_exhausted")
    if snapshot.active_training_jobs:
        return RecoveryDecision("wait", "training_active")
    evaluator_terminal = classify_state(evaluator_status.state).terminal
    if snapshot.unscored_claims and not evaluator_terminal:
        return RecoveryDecision("wait", "evaluation_active")
    if receipt == "halt" or receipt == "complete":
        return RecoveryDecision("halt", f"controller_receipt_{receipt}")
    if terminal.state == "CANCELLED":
        return RecoveryDecision("halt", "slurm_cancelled")
    if terminal.retryable:
        return RecoveryDecision("recover", f"slurm_{terminal.state.lower()}")
    if receipt == "recover":
        return RecoveryDecision("recover", "controller_receipt_recover")
    return RecoveryDecision("halt", "terminal_failure_not_retryable")


class Supervisor:
    def __init__(self, args: argparse.Namespace) -> None:
        self.attempt = args.attempt.resolve(strict=True)
        self.resume_script = args.resume_script.resolve(strict=True)
        self.seeds = tuple(args.seeds)
        self.target_pairs = args.target_pairs
        self.session_ceiling = args.session_ceiling
        self.max_restarts = args.max_restarts
        self.max_plan_failures = args.max_plan_failures
        self.poll_seconds = args.poll_seconds
        self.backoff_seconds = args.backoff_seconds
        self.unknown_state_timeout_seconds = args.unknown_state_timeout_seconds
        self.once = args.once
        self.metadata = self.attempt / "metadata"
        self.state_path = self.metadata / "controller_supervisor.json"
        self.events_path = self.metadata / "controller_supervisor_events.jsonl"
        self.state = self._load_state()

    def _load_state(self) -> dict[str, object]:
        value = _read_json(self.state_path)
        if value is None:
            value = {
                "schema": STATE_SCHEMA,
                "chains": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        if value.get("schema") != STATE_SCHEMA or not isinstance(
            value.get("chains"), dict
        ):
            raise RuntimeError("invalid controller-supervisor state")
        chains = value["chains"]
        assert isinstance(chains, dict)
        for seed in self.seeds:
            chains.setdefault(
                seed,
                {
                    "restart_count": 0,
                    "plan_failures": 0,
                    "status": "watching",
                    "next_attempt_after": 0,
                },
            )
        registry = self.metadata / "recovery_jobs.tsv"
        if registry.is_file():
            supervised = {seed: 0 for seed in self.seeds}
            for raw in registry.read_text(encoding="utf-8").splitlines():
                fields = raw.split("\t")
                if len(fields) < 6:
                    continue
                _timestamp, kind, seed, job, _commit, details = fields[:6]
                if (
                    kind == "chain"
                    and seed in supervised
                    and job.isdigit()
                    and "origin=supervisor" in details.split(";")
                ):
                    supervised[seed] += 1
            for seed, count in supervised.items():
                chain = chains[seed]
                assert isinstance(chain, dict)
                chain["restart_count"] = max(
                    int(chain.get("restart_count", 0)), count
                )
        return value

    def _save(self) -> None:
        self.state["updated_at"] = datetime.now(timezone.utc).isoformat()
        _atomic_write_json(self.state_path, self.state)

    def _event(self, seed: str, action: str, **details: object) -> None:
        value = {
            "schema": EVENT_SCHEMA,
            "at": datetime.now(timezone.utc).isoformat(),
            "seed": seed,
            "action": action,
            **details,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(
            f"[controller-supervisor] seed={seed} action={action} "
            + " ".join(f"{key}={value}" for key, value in details.items()),
            flush=True,
        )

    @staticmethod
    def _job_status(job: str) -> JobStatus:
        completed = subprocess.run(
            [
                "sacct",
                "-j",
                job,
                "-X",
                "-n",
                "-P",
                "-o",
                "State,ExitCode",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return JobStatus("", "")
        for line in completed.stdout.splitlines():
            fields = line.split("|")
            if fields and fields[0].strip():
                return JobStatus(
                    fields[0].strip().split()[0].rstrip("+"),
                    fields[1].strip() if len(fields) > 1 else "",
                )
        return JobStatus("", "")

    def _run_recovery(self, seed: str, *, plan_only: bool) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        repository = self.resume_script.parents[4]
        branch = subprocess.run(
            ["git", "-C", str(repository), "branch", "--show-current"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if branch:
            environment.pop("AAR_RESUME_ALLOW_DETACHED_SOURCE", None)
        else:
            environment["AAR_RESUME_ALLOW_DETACHED_SOURCE"] = "1"
        environment["AAR_RESUME_REUSE_EVALUATOR"] = "1"
        environment["AAR_RESUME_REQUIRE_AUTHORITATIVE_JOB_STATE"] = "1"
        environment["AAR_RESUME_RECOVERY_ORIGIN"] = "supervisor"
        if plan_only:
            environment["AAR_RESUME_PLAN_ONLY"] = "1"
        else:
            environment.pop("AAR_RESUME_PLAN_ONLY", None)
        return subprocess.run(
            [str(self.resume_script), str(self.attempt), seed],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    def run_once(self) -> bool:
        controllers, evaluators = read_latest_jobs(self.attempt, self.seeds)
        all_terminal = True
        chains = self.state["chains"]
        assert isinstance(chains, dict)
        for seed in self.seeds:
            chain_state = chains[seed]
            assert isinstance(chain_state, dict)
            if chain_state.get("status") in {"complete", "halted"}:
                continue
            all_terminal = False
            controller = controllers[seed]
            evaluator = evaluators[seed]
            team = team_for_seed(self.attempt, seed)
            controller_status = self._job_status(controller)
            evaluator_status = self._job_status(evaluator)
            if not controller_status.state:
                unknown_since = int(chain_state.get("unknown_since", 0))
                if not unknown_since:
                    unknown_since = int(time.time())
                    chain_state["unknown_since"] = unknown_since
                    self._event(
                        seed, "wait", reason="scheduler_state_unknown", job=controller
                    )
                elif time.time() - unknown_since >= self.unknown_state_timeout_seconds:
                    chain_state["status"] = "halted"
                    chain_state["reason"] = "scheduler_state_unknown_timeout"
                    self._event(
                        seed,
                        "halt",
                        reason="scheduler_state_unknown_timeout",
                        job=controller,
                    )
                continue
            chain_state.pop("unknown_since", None)
            if classify_state(controller_status.state).terminal:
                reconcile_session_result(
                    team
                    / "logs"
                    / f"research-session-result-{controller}.json",
                    job_id=controller,
                    slurm_state=controller_status.state,
                    slurm_exit_code=controller_status.exit_code or "unknown",
                )
            if not evaluator_status.state:
                reason = "evaluator_scheduler_state_unknown"
                if chain_state.get("last_reason") != reason:
                    self._event(seed, "wait", reason=reason, job=evaluator)
                chain_state["last_reason"] = reason
                continue
            snapshot = ChainSnapshot(
                seed=seed,
                controller_job=controller,
                evaluator_job=evaluator,
                pairs=count_pairs(team),
                sessions=count_sessions(team, seed),
                active_training_jobs=active_training_jobs(team, self._job_status),
                unscored_claims=unscored_claims(team),
            )
            decision = decide_recovery(
                snapshot,
                controller_status,
                evaluator_status,
                receipt=receipt_disposition(team, controller),
                target_pairs=self.target_pairs,
                session_ceiling=self.session_ceiling,
                restart_count=int(chain_state.get("restart_count", 0)),
                max_restarts=self.max_restarts,
            )
            if decision.action == "complete":
                chain_state["status"] = "complete"
                self._event(seed, "complete", reason=decision.reason, pairs=snapshot.pairs)
            elif decision.action == "halt":
                chain_state["status"] = "halted"
                chain_state["reason"] = decision.reason
                self._event(seed, "halt", reason=decision.reason, job=controller)
            elif decision.action in {"watch", "wait"}:
                if chain_state.get("last_reason") != decision.reason:
                    self._event(seed, decision.action, reason=decision.reason, job=controller)
                chain_state["last_reason"] = decision.reason
            elif time.time() < int(chain_state.get("next_attempt_after", 0)):
                continue
            else:
                plan = self._run_recovery(seed, plan_only=True)
                if plan.returncode != 0:
                    failures = int(chain_state.get("plan_failures", 0)) + 1
                    chain_state["plan_failures"] = failures
                    chain_state["next_attempt_after"] = int(time.time()) + self.backoff_seconds
                    self._event(
                        seed,
                        "plan_failed",
                        returncode=plan.returncode,
                        failures=failures,
                    )
                    if failures >= self.max_plan_failures:
                        chain_state["status"] = "halted"
                        chain_state["reason"] = "recovery_plan_failure_limit"
                        self._event(seed, "halt", reason="recovery_plan_failure_limit")
                else:
                    resumed = self._run_recovery(seed, plan_only=False)
                    if resumed.returncode != 0:
                        failures = int(chain_state.get("plan_failures", 0)) + 1
                        chain_state["plan_failures"] = failures
                        chain_state["next_attempt_after"] = int(time.time()) + self.backoff_seconds
                        self._event(
                            seed,
                            "resume_failed",
                            returncode=resumed.returncode,
                            failures=failures,
                        )
                        if failures >= self.max_plan_failures:
                            chain_state["status"] = "halted"
                            chain_state["reason"] = "recovery_launch_failure_limit"
                            self._event(
                                seed,
                                "halt",
                                reason="recovery_launch_failure_limit",
                            )
                    else:
                        chain_state["restart_count"] = int(
                            chain_state.get("restart_count", 0)
                        ) + 1
                        chain_state["plan_failures"] = 0
                        chain_state["next_attempt_after"] = int(time.time()) + self.backoff_seconds
                        chain_state["last_reason"] = "resumed"
                        self._event(
                            seed,
                            "resumed",
                            prior_job=controller,
                            restart_count=chain_state["restart_count"],
                        )
        self._save()
        return all_terminal

    def run(self) -> int:
        stop = self.metadata / "controller_supervisor.stop"
        pause = self.metadata / "controller_supervisor.pause"
        while True:
            if stop.exists():
                self._event("-", "stop", reason="operator_stop_marker")
                return 0
            if pause.exists():
                time.sleep(self.poll_seconds)
                continue
            if self.run_once():
                return 0
            if self.once:
                return 0
            time.sleep(self.poll_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--resume-script", type=Path, required=True)
    parser.add_argument("--seeds", nargs="+", required=True)
    parser.add_argument("--target-pairs", type=int, required=True)
    parser.add_argument("--session-ceiling", type=int, required=True)
    parser.add_argument("--max-restarts", type=int, required=True)
    parser.add_argument("--max-plan-failures", type=int, required=True)
    parser.add_argument("--poll-seconds", type=int, required=True)
    parser.add_argument("--backoff-seconds", type=int, required=True)
    parser.add_argument("--unknown-state-timeout-seconds", type=int, required=True)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    lock_path = args.attempt / "metadata" / "controller_supervisor.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("another controller supervisor owns this attempt", flush=True)
            return 2
        return Supervisor(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
