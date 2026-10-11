"""Contracts for state-preserving multi-team AAR recovery."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / "resume_aar_multiteam.sh"
RUN14_RECOVERY = (
    ROOT
    / "experiments"
    / "dishonest_sycophancy_concealing"
    / "run_14"
    / "recovery"
    / "resume_full.sh"
)


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source)
    path.chmod(0o755)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    fake_bin = tmp_path / "bin"
    attempt = tmp_path / "attempt"
    metadata = attempt / "metadata"
    for path in (repo / "aar", scripts, fake_bin, metadata, attempt / "aar_teams"):
        path.mkdir(parents=True, exist_ok=True)

    shutil.copy2(ENGINE, scripts / ENGINE.name)
    _write_executable(
        scripts / "aar_runtime_env.sh",
        "#!/bin/bash\n"
        "AAR_RESEARCH_CHAIN_ENV_ALLOWLIST=(\n"
        "  AAR_REPO AAR_RUNTIME_ROOT TEAM_DIR AAR_AUTODATA AAR_NO_LOCAL_GPU\n"
        "  AAR_TARGET_SUCCESSFUL_ITERATIONS AAR_REQUIRE_TRAIN_RECEIPT\n"
        "  AAR_IDEA_UID_OVERRIDE AAR_RESUME_APPROVED_PROPOSAL\n"
        ")\n",
    )
    _write_executable(scripts / "slurm_aar_chain.sh", "#!/bin/bash\nexit 0\n")
    _write_executable(
        scripts / "repair_approved_proposal_run_id.py",
        "#!/usr/bin/env python3\n"
        "import json,os,sys\n"
        'idea_uid = sys.argv[sys.argv.index("--idea-uid") + 1]\n'
        'team_dir = sys.argv[sys.argv.index("--team-dir") + 1]\n'
        'plan_only = int("--plan-only" in sys.argv)\n'
        'with open(os.environ["REPAIR_LOG"], "a") as stream:\n'
        '    stream.write(f"{idea_uid}|{plan_only}\\n")\n'
        'marker = os.path.join(team_dir, "scores", ".proposals", f"{idea_uid}.json")\n'
        'run_id = json.load(open(marker)).get("run_id")\n'
        'print(run_id or f"{idea_uid}-repaired")\n',
    )
    _write_executable(
        scripts / "launch_eval_worker.sh",
        "#!/bin/bash\n"
        "set -eu\n"
        'n="$(cat "$JOB_COUNTER")"; n=$((n + 1)); printf "%s\\n" "$n" > "$JOB_COUNTER"\n'
        'job=$((7000 + n)); printf "%s|%s\\n" "$TEAM_ID" "$job" >> "$EVAL_LOG"\n'
        'printf "[launch] evaluator 1/1 -> job %s\\n" "$job"\n',
    )
    _write_executable(
        fake_bin / "squeue",
        "#!/bin/bash\n"
        "job=\n"
        'while [ "$#" -gt 0 ]; do if [ "$1" = -j ]; then shift; job="$1"; fi; shift; done\n'
        'case ",${ACTIVE_JOBS:-}," in *",${job},"*) echo RUNNING;; esac\n',
    )
    _write_executable(
        fake_bin / "sacct",
        "#!/bin/bash\n"
        "job=\n"
        'while [ "$#" -gt 0 ]; do if [ "$1" = -j ]; then shift; job="$1"; fi; shift; done\n'
        'for pair in ${JOB_STATES:-}; do '
        'case "$pair" in "$job"=*) printf "%s|\\n" "${pair#*=}"; exit 0;; esac; '
        "done\n",
    )
    _write_executable(
        fake_bin / "sbatch",
        "#!/bin/bash\n"
        "set -eu\n"
        'n="$(cat "$JOB_COUNTER")"; n=$((n + 1)); printf "%s\\n" "$n" > "$JOB_COUNTER"\n'
        'job=$((9000 + n)); printf "%s|%s|%s|%s|%s\\n" '
        '"$TEAM_ID" "${AAR_IDEA_UID_OVERRIDE:-}" '
        '"${AAR_RESUME_APPROVED_PROPOSAL:-}" "$job" "$*" >> "$SBATCH_LOG"\n'
        'printf "%s\\n" "$job"\n',
    )

    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.name=AAR Test",
        "-c",
        "user.email=aar-test@example.com",
        "commit",
        "-qm",
        "fixture",
    )
    commit = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")

    (metadata / "submission.txt").write_text(
        f"attempt_dir={attempt}\nmode=full\ngit_commit={commit}\n"
    )
    (metadata / "children.tsv").write_text(
        "alpha\t101\t102\n"
        "beta\t103\t104\n"
        "gamma\t105\t106\n"
        "delta\t107\t108\n"
        "epsilon\t109\t110\n"
    )

    for seed, sessions in (
        ("alpha", 2),
        ("beta", 1),
        ("gamma", 3),
        ("delta", 2),
        ("epsilon", 3),
    ):
        team = attempt / "aar_teams" / f"team-{seed}-launch"
        for directory in (
            "logs",
            "scores/.proposals/runs",
            "scores/.claims",
            "submissions",
            "methods",
            "forum",
            "litreview",
            ".finding_dedup",
            ".train_submissions",
            "_train",
            "timings",
            "_eval_private/timings",
        ):
            (team / directory).mkdir(parents=True, exist_ok=True)
        for index in range(sessions):
            (team / "logs" / f"session_{index:03d}_model_{seed}_stamp.log").touch()
        idea_uid = f"idea-{seed}"
        run_id = f"{idea_uid}-run"
        proposal = (
            '{"approved":true,"idea_uid":"%s","idea_name":"method_%s",'
            '"run_id":"%s","code_hash":"abc","ts":1}\n'
            % (idea_uid, seed, run_id)
        )
        (team / "scores" / ".proposals" / f"{idea_uid}.json").write_text(proposal)

    alpha = attempt / "aar_teams" / "team-alpha-launch"
    alpha_score = alpha / "scores" / "idea-alpha-run.json"
    alpha_score.write_text('{"run_id":"idea-alpha-run","score":1}\n')
    (alpha / "scores" / ".claims" / "idea-alpha-run").mkdir()

    beta = attempt / "aar_teams" / "team-beta-launch"
    (beta / "scores" / "idea-beta-run.json").write_text(
        '{"run_id":"idea-beta-run","score":1}\n'
    )
    (beta / "scores" / ".claims" / "idea-beta-run").mkdir()

    gamma = attempt / "aar_teams" / "team-gamma-launch"
    gamma_submission = gamma / "submissions" / "idea-gamma-run"
    gamma_submission.mkdir()
    (gamma_submission / ".submitted").touch()
    (gamma / "scores" / ".claims" / "idea-gamma-run").mkdir()
    (gamma / "_eval_private" / "timings" / "idea-gamma-run.eval.jsonl").write_text(
        '{"phase":"eval.benchmark","status":"success"}\n'
    )
    old_score = gamma / "scores" / "old-pair.json"
    old_score.write_text('{"run_id":"old-pair","score":2}\n')
    old_finding = gamma / ".finding_dedup" / "runid_old-pair"
    old_finding.mkdir()
    (old_finding / "post.json").write_text('{"run_id":"old-pair","post_id":"p"}\n')

    delta = attempt / "aar_teams" / "team-delta-launch"
    delta_submission = delta / "submissions" / "idea-delta-run"
    delta_submission.mkdir()
    (delta_submission / ".submitted").touch()
    (delta / "scores" / ".claims" / "idea-delta-run").mkdir()
    (delta / "_eval_private" / "timings" / "idea-delta-run.eval.jsonl").write_text(
        '{"phase":"eval.benchmark","status":"success"}\n'
    )

    epsilon = attempt / "aar_teams" / "team-epsilon-launch"
    (epsilon / ".train_submissions" / "idea-epsilon-run.env").write_text(
        "run_id=idea-epsilon-run\njob_id=301\n"
    )
    staging = epsilon / "_train" / "idea-epsilon-run"
    staging.mkdir()
    (staging / "partial").write_text("retained\n")
    (epsilon / "timings" / "idea-epsilon-run.research.jsonl").write_text(
        '{"phase":"train.method_total","status":"running"}\n'
    )

    counter = tmp_path / "counter"
    counter.write_text("0\n")
    eval_log = tmp_path / "eval.log"
    sbatch_log = tmp_path / "sbatch.log"
    repair_log = tmp_path / "repair.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "AAR_REPO": str(repo),
        "HARNESS_PY": sys.executable,
        "AAR_RUNTIME_ROOT": str(attempt),
        "AAR_AUTODATA": "0",
        "AAR_NO_LOCAL_GPU": "true",
        "AAR_TARGET_SUCCESSFUL_ITERATIONS": "50",
        "AAR_REQUIRE_TRAIN_RECEIPT": "1",
        "AAR_CHAIN_SANITIZE_ENV": "1",
        "SUITE_NAME": "test_suite",
        "AAR_RESUME_EXPECTED_BRANCH": branch,
        "AAR_RESUME_EXPECTED_MODE": "full",
        "AAR_RESUME_ALLOWED_SEEDS": "alpha beta gamma delta epsilon",
        "AAR_RESUME_DEFAULT_SEEDS": "alpha beta gamma delta epsilon",
        "AAR_RESUME_TEAM_PREFIX": "team-",
        "AAR_RESUME_TEAM_SUFFIX": "-launch",
        "AAR_RESUME_MAX_SESSIONS": "60",
        "AAR_RESUME_HOURS": "12",
        "AAR_RESUME_JOB_PREFIX": "aar-test",
        "AAR_RESUME_RETRY_INTERRUPTED_TRAINING": "1",
        "AAR_RESUME_CONFIG_SHA256": "fixture-config-sha256",
        "AAR_RESUME_EXPECTED_REMAINING": (
            "alpha=58 beta=59 gamma=57 delta=58 epsilon=57"
        ),
        "AAR_EVAL_IDLE_SECONDS": "600",
        "AAR_SLURM_ACCOUNT": "account",
        "AAR_SLURM_PARTITION": "partition",
        "AAR_AGENT_QOS": "qos",
        "JOB_STATES": "301=CANCELLED",
        "MODEL_API_KEY": "must-not-reach-research",
        "HF_TOKEN": "must-not-reach-research",
        "HARNESS_ENV": "/secret/operator.env",
        "JOB_COUNTER": str(counter),
        "EVAL_LOG": str(eval_log),
        "SBATCH_LOG": str(sbatch_log),
        "REPAIR_LOG": str(repair_log),
    }
    return repo, attempt, fake_bin, env


def test_multiteam_resume_preserves_results_and_recovers_interrupted_work(
    tmp_path: Path,
) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    alpha_score = (
        attempt
        / "aar_teams"
        / "team-alpha-launch"
        / "scores"
        / "idea-alpha-run.json"
    )
    old_score = (
        attempt / "aar_teams" / "team-gamma-launch" / "scores" / "old-pair.json"
    )
    old_finding = (
        attempt
        / "aar_teams"
        / "team-gamma-launch"
        / ".finding_dedup"
        / "runid_old-pair"
        / "post.json"
    )
    before = tuple(_sha256(path) for path in (alpha_score, old_score, old_finding))

    completed = subprocess.run(
        [str(repo / "scripts" / ENGINE.name), str(attempt)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert tuple(_sha256(path) for path in (alpha_score, old_score, old_finding)) == before
    alpha_claim = (
        attempt
        / "aar_teams"
        / "team-alpha-launch"
        / "scores"
        / ".claims"
        / "idea-alpha-run"
    )
    assert alpha_claim.is_dir(), "a completed score's claim must not be retired"

    archive_roots = list((attempt / "metadata" / "recovery_archive").iterdir())
    assert len(archive_roots) == 1
    archive = archive_roots[0]
    assert (archive / "gamma" / "eval_claims" / "idea-gamma-run").is_dir()
    assert (
        archive
        / "gamma"
        / "eval_timings"
        / "idea-gamma-run.eval.jsonl"
    ).is_file()
    assert (archive / "delta" / "eval_claims" / "idea-delta-run").is_dir()
    assert (
        archive
        / "delta"
        / "eval_timings"
        / "idea-delta-run.eval.jsonl"
    ).is_file()
    epsilon_archive = archive / "epsilon" / "training" / "idea-epsilon-run"
    assert (epsilon_archive / "receipt.env").is_file()
    assert (epsilon_archive / "idea-epsilon-run" / "partial").read_text() == "retained\n"
    assert (epsilon_archive / "idea-epsilon-run.research.jsonl").is_file()

    epsilon = attempt / "aar_teams" / "team-epsilon-launch"
    assert not (epsilon / ".train_submissions" / "idea-epsilon-run.env").exists()
    assert not (epsilon / "_train" / "idea-epsilon-run").exists()

    registry = (attempt / "metadata" / "recovery_jobs.tsv").read_text()
    assert "\trecovery_start\t-\t-\t" in registry
    assert "config_sha256=fixture-config-sha256" in registry
    assert "\tclaim_retired\tgamma\t-\t" in registry
    assert "\ttraining_attempt_retired\tepsilon\t301\t" in registry
    assert registry.count("\tevaluator\t") == 5
    assert registry.count("\tchain\t") == 5

    submissions = Path(env["SBATCH_LOG"]).read_text().splitlines()
    assert any("team-alpha-launch|idea-alpha|1|" in line and " 58 " in line for line in submissions)
    assert any("team-beta-launch|idea-beta|1|" in line and " 59 " in line for line in submissions)
    assert any("team-gamma-launch|idea-gamma|1|" in line and " 57 " in line for line in submissions)
    assert any("team-delta-launch|idea-delta|1|" in line and " 58 " in line for line in submissions)
    assert any("team-epsilon-launch|idea-epsilon|1|" in line and " 57 " in line for line in submissions)
    for line in submissions:
        assert "--export=" in line
        assert "MODEL_API_KEY" not in line
        assert "HF_TOKEN" not in line
        assert "HARNESS_ENV" not in line
        assert "AAR_IDEA_UID_OVERRIDE" in line
        assert "AAR_RESUME_APPROVED_PROPOSAL" in line
        assert "AAR_NO_LOCAL_GPU" in line
        assert "TEAM_DIR" in line
    assert "alpha: 2/60 started" in completed.stdout
    assert "beta: 1/60 started" in completed.stdout
    assert "gamma: 3/60 started" in completed.stdout
    assert "delta: 2/60 started" in completed.stdout
    assert "epsilon: 3/60 started" in completed.stdout


def test_multiteam_resume_rejects_active_job_before_retiring_state(tmp_path: Path) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    env["ACTIVE_JOBS"] = "105"
    claim = (
        attempt
        / "aar_teams"
        / "team-gamma-launch"
        / "scores"
        / ".claims"
        / "idea-gamma-run"
    )

    completed = subprocess.run(
        [str(repo / "scripts" / ENGINE.name), str(attempt)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 2
    assert "attempt job(s) remain active: 105" in completed.stderr
    assert claim.is_dir()
    assert not (attempt / "metadata" / "recovery_archive").exists()
    assert not Path(env["SBATCH_LOG"]).exists()


def test_partial_resume_ignores_active_jobs_for_unrequested_teams(
    tmp_path: Path,
) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    env["ACTIVE_JOBS"] = "105"
    env["AAR_RESUME_PLAN_ONLY"] = "1"

    completed = subprocess.run(
        [
            str(repo / "scripts" / ENGINE.name),
            str(attempt),
            "alpha beta",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "alpha: started=2 remaining=58" in completed.stdout
    assert "beta: started=1 remaining=59" in completed.stdout
    assert "gamma:" not in completed.stdout
    assert not (attempt / "metadata" / "recovery_archive").exists()


def test_partial_resume_selects_latest_proposal_marker(tmp_path: Path) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    env["AAR_RESUME_PLAN_ONLY"] = "1"
    proposals = (
        attempt
        / "aar_teams"
        / "team-alpha-launch"
        / "scores"
        / ".proposals"
    )
    (proposals / "idea-alpha-new.json").write_text(
        '{"approved":true,"idea_uid":"idea-alpha-new",'
        '"idea_name":"method_alpha","run_id":"idea-alpha-new-run",'
        '"code_hash":"def","ts":2}\n'
    )
    submission = (
        attempt
        / "aar_teams"
        / "team-alpha-launch"
        / "submissions"
        / "idea-alpha-new-run"
    )
    submission.mkdir()
    (submission / ".submitted").touch()

    completed = subprocess.run(
        [
            str(repo / "scripts" / ENGINE.name),
            str(attempt),
            "alpha",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "resume_run_id=idea-alpha-new-run" in completed.stdout


def test_run14_recovery_declares_decoupled_execution() -> None:
    source = RUN14_RECOVERY.read_text()

    assert "export AAR_NO_LOCAL_GPU=true" in source


def test_missing_run_id_is_planned_without_mutation(tmp_path: Path) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    env["AAR_RESUME_PLAN_ONLY"] = "1"
    marker = (
        attempt
        / "aar_teams"
        / "team-alpha-launch"
        / "scores"
        / ".proposals"
        / "idea-alpha.json"
    )
    payload = json.loads(marker.read_text())
    payload.pop("run_id")
    payload["execution_ready"] = True
    marker.write_text(json.dumps(payload))
    before = marker.read_bytes()

    completed = subprocess.run(
        [
            str(repo / "scripts" / ENGINE.name),
            str(attempt),
            "alpha",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "resume_run_id=idea-alpha-repaired" in completed.stdout
    assert marker.read_bytes() == before
    assert Path(env["REPAIR_LOG"]).read_text() == "idea-alpha|1\n"


def test_completed_latest_proposal_skips_current_method_validation(
    tmp_path: Path,
) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    env["AAR_RESUME_PLAN_ONLY"] = "1"
    team = attempt / "aar_teams" / "team-alpha-launch"
    finding = team / ".finding_dedup" / "runid_idea-alpha-run"
    finding.mkdir()
    (finding / "post.json").write_text(
        '{"run_id":"idea-alpha-run","post_id":"done"}\n'
    )
    # Models share a method file across sessions.  Its contents may have moved
    # on after a prior proposal completed, which must not invalidate recovery.
    (team / "methods" / "method_alpha.py").write_text("later session draft\n")

    completed = subprocess.run(
        [str(repo / "scripts" / ENGINE.name), str(attempt), "alpha"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "resume_run_id=none" in completed.stdout
    assert not Path(env["REPAIR_LOG"]).exists()


def test_missing_run_id_is_repaired_and_audited_before_launch(
    tmp_path: Path,
) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    marker = (
        attempt
        / "aar_teams"
        / "team-alpha-launch"
        / "scores"
        / ".proposals"
        / "idea-alpha.json"
    )
    payload = json.loads(marker.read_text())
    payload.pop("run_id")
    payload["execution_ready"] = True
    marker.write_text(json.dumps(payload))

    completed = subprocess.run(
        [
            str(repo / "scripts" / ENGINE.name),
            str(attempt),
            "alpha",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert Path(env["REPAIR_LOG"]).read_text() == (
        "idea-alpha|1\nidea-alpha|0\n"
    )
    registry = (attempt / "metadata" / "recovery_jobs.tsv").read_text()
    assert "\tproposal_run_id_repaired\talpha\t-\t" in registry
    assert "run_id=idea-alpha-repaired" in registry


def test_recovery_rejects_missing_decoupled_execution_flag(tmp_path: Path) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    env.pop("AAR_NO_LOCAL_GPU")

    completed = subprocess.run(
        [str(repo / "scripts" / ENGINE.name), str(attempt), "alpha"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 2
    assert "requires AAR_NO_LOCAL_GPU=true" in completed.stderr
    assert not (attempt / "metadata" / "recovery_archive").exists()


def test_multiteam_plan_only_validates_exact_budgets_without_changes(
    tmp_path: Path,
) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    env["AAR_RESUME_PLAN_ONLY"] = "1"
    claim = (
        attempt
        / "aar_teams"
        / "team-gamma-launch"
        / "scores"
        / ".claims"
        / "idea-gamma-run"
    )
    receipt = (
        attempt
        / "aar_teams"
        / "team-epsilon-launch"
        / ".train_submissions"
        / "idea-epsilon-run.env"
    )

    completed = subprocess.run(
        [str(repo / "scripts" / ENGINE.name), str(attempt)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "alpha: started=2 remaining=58" in completed.stdout
    assert "beta: started=1 remaining=59" in completed.stdout
    assert "gamma: started=3 remaining=57" in completed.stdout
    assert "delta: started=2 remaining=58" in completed.stdout
    assert "epsilon: started=3 remaining=57" in completed.stdout
    assert "stale_claims=2 stale_eval_timings=2; no state changed" in completed.stdout
    assert claim.is_dir()
    assert receipt.is_file()
    assert not (attempt / "metadata" / "recovery_archive").exists()
    assert not Path(env["SBATCH_LOG"]).exists()


def test_cancelled_training_failure_is_archived_before_same_run_retry(
    tmp_path: Path,
) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    epsilon = attempt / "aar_teams" / "team-epsilon-launch"
    failure = epsilon / "scores" / "idea-epsilon-run.failed.json"
    failure.write_text(
        '{"run_id":"idea-epsilon-run","stage":"training",'
        '"error_code":"training_process_failed"}\n'
    )

    completed = subprocess.run(
        [str(repo / "scripts" / ENGINE.name), str(attempt)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    archive = next((attempt / "metadata" / "recovery_archive").iterdir())
    retired_failure = (
        archive
        / "epsilon"
        / "training"
        / "idea-epsilon-run"
        / "prior_failure.json"
    )
    assert retired_failure.is_file()
    assert not failure.exists()
    assert any(
        "team-epsilon-launch|idea-epsilon|1|" in line
        for line in Path(env["SBATCH_LOG"]).read_text().splitlines()
    )


def test_multiteam_resume_rejects_unsubmitted_unscored_claim(tmp_path: Path) -> None:
    repo, attempt, _fake_bin, env = _fixture(tmp_path)
    gamma = attempt / "aar_teams" / "team-gamma-launch"
    (gamma / "submissions" / "idea-gamma-run" / ".submitted").unlink()

    completed = subprocess.run(
        [str(repo / "scripts" / ENGINE.name), str(attempt)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 2
    assert "unscored claim has no submitted adapter" in completed.stderr
    assert (gamma / "scores" / ".claims" / "idea-gamma-run").is_dir()
    assert not (attempt / "metadata" / "recovery_archive").exists()


def test_run14_wrapper_is_fail_closed_and_delegates_to_shared_engine() -> None:
    subprocess.run(["bash", "-n", str(RUN14_RECOVERY)], check=True)
    source = RUN14_RECOVERY.read_text()

    assert 'git -C "${REPO}" show' in source
    assert '"${original_commit}:experiments/dishonest_sycophancy_concealing/run_14/config/run.yaml"' in source
    assert '[ "${retained_config_sha256}" = "${original_config_sha256}" ]' in source
    assert "normalized_recovery_config_sha256" in source
    assert "differs from the attempt by more than vllm_log_stats=true" in source
    assert 'merge-base --is-ancestor "${original_commit}" HEAD' in source
    assert '[ "${AAR_AUTODATA:?missing data-generation backend}" = 0 ]' in source
    assert 'while IFS= read -r name; do unset "${name}"; done' in source
    assert '[ "${AAR_TARGET_SUCCESSFUL_ITERATIONS:?}" = 50 ]' in source
    assert '[ "${AAR_MAX_ITERATIONS_PER_CHAIN:?}" = 60 ]' in source
    assert '[ "${EVAL_VLLM_LOG_STATS:?missing vLLM telemetry policy}" = 1 ]' in source
    assert "requires evaluation.vllm_log_stats=true" in source
    assert 'AAR_RESUME_TEAM_SUFFIX="-${launch_job}"' in source
    assert "AAR_RESUME_RETRY_INTERRUPTED_TRAINING=1" in source
    assert 'AAR_RESUME_CONFIG_SHA256="$(sha256sum -- "${CANONICAL_CONFIG}"' in source
    assert 'exec "${REPO}/scripts/resume_aar_multiteam.sh"' in source
