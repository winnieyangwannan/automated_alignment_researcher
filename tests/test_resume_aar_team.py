"""End-to-end shell contract for reusable AAR chain recovery."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


def test_shared_resume_replenishes_evaluator_and_only_restarts_selected_chain(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    fake_bin = tmp_path / "bin"
    attempt = tmp_path / "attempt"
    team = attempt / "aar_teams" / "team-one"
    for path in (repo / "aar", scripts, fake_bin, team / "logs", attempt / "metadata"):
        path.mkdir(parents=True, exist_ok=True)

    shutil.copy2(ROOT / "scripts" / "resume_aar_team.sh", scripts)
    _write_executable(scripts / "slurm_aar_chain.sh", "#!/bin/bash\nexit 0\n")
    _write_executable(
        scripts / "launch_eval_worker.sh",
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" > "$EVAL_LAUNCH_ARGS"\n'
        'printf "[launch] evaluator 1/1 -> job 7001\\n"\n',
    )
    _write_executable(
        fake_bin / "squeue",
        "#!/bin/bash\n"
        "job=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = -j ]; then shift; job=\"$1\"; fi\n"
        "  shift\n"
        "done\n"
        'case ",${ACTIVE_JOBS:-}," in *",${job},"*) echo RUNNING;; esac\n',
    )
    _write_executable(
        fake_bin / "sbatch",
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" > "$SBATCH_ARGS"\n'
        "echo 9001\n",
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

    (attempt / "metadata" / "submission.txt").write_text(
        f"mode=full\ngit_commit={commit}\n"
    )
    (attempt / "metadata" / "children.env").write_text(
        "evaluator_jobs=201\n"
        "research_chain_jobs=101 102\n"
        "research_seeds=alpha beta\n"
        "max_iterations_per_chain=5\n"
    )
    for index in range(3):
        (team / "logs" / f"session_{index:03d}_alpha_20260101.log").touch()

    sbatch_args = tmp_path / "sbatch.args"
    eval_launch_args = tmp_path / "eval.args"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "AAR_REPO": str(repo),
        "SUITE_NAME": "test_suite",
        "MODEL": "test_model",
        "AAR_RESUME_EXPECTED_BRANCH": branch,
        "AAR_RESUME_EXPECTED_MODE": "full",
        "AAR_RESUME_ALLOWED_SEEDS": "alpha beta",
        "AAR_RESUME_EVALUATOR_COUNT": "2",
        "AAR_RESUME_HOURS": "12",
        "AAR_RESUME_JOB_PREFIX": "aar-test",
        "AAR_EVAL_IDLE_SECONDS": "600",
        "AAR_SLURM_ACCOUNT": "account",
        "AAR_SLURM_PARTITION": "partition",
        "AAR_AGENT_QOS": "qos",
        "ACTIVE_JOBS": "201,102",
        "SBATCH_ARGS": str(sbatch_args),
        "EVAL_LAUNCH_ARGS": str(eval_launch_args),
    }
    completed = subprocess.run(
        [str(scripts / "resume_aar_team.sh"), str(attempt), "alpha"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert "alpha: 3/5 started, job 9001 receives 2 remaining sessions" in completed.stdout
    assert eval_launch_args.read_text().strip() == "test_suite 600 1"
    submitted = sbatch_args.read_text()
    assert "--time=12:30:00" in submitted
    assert "explore-alpha 12 2 team-one" in submitted
    registry = (attempt / "metadata" / "recovery_jobs.tsv").read_text()
    assert "\tevaluator\t-\t7001\t" in registry
    assert "\tchain\talpha\t9001\t" in registry
    assert "remaining=2" in registry

    duplicate = subprocess.run(
        [str(scripts / "resume_aar_team.sh"), str(attempt), "beta"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert duplicate.returncode == 2
    assert "refusing duplicate active chain for seed beta" in duplicate.stderr
