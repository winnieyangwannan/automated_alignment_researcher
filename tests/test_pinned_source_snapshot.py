from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "scripts" / "create_pinned_source_snapshot.sh"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True
    ).strip()


def _source_repo(tmp_path: Path) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    _git(source, "config", "user.name", "Snapshot Test")
    _git(source, "config", "user.email", "snapshot@example.invalid")
    (source / "version.txt").write_text("one\n")
    _git(source, "add", "version.txt")
    _git(source, "commit", "-qm", "one")
    return source, _git(source, "rev-parse", "HEAD")


def test_snapshot_remains_pinned_after_shared_checkout_advances(tmp_path: Path) -> None:
    source, first_commit = _source_repo(tmp_path)
    destination = tmp_path / "attempt" / "runtime" / "aar-source"

    completed = subprocess.run(
        [str(SNAPSHOT), str(source), first_commit, str(destination)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert completed.stdout.strip() == str(destination)

    (source / "version.txt").write_text("two\n")
    _git(source, "add", "version.txt")
    _git(source, "commit", "-qm", "two")

    assert (destination / "version.txt").read_text() == "one\n"
    assert _git(destination, "rev-parse", "HEAD") == first_commit
    assert _git(destination, "branch", "--show-current") == ""
    assert _git(destination, "remote") == ""
    assert not (destination / ".git" / "objects" / "info" / "alternates").exists()


def test_snapshot_refuses_to_overwrite_an_existing_destination(tmp_path: Path) -> None:
    source, commit = _source_repo(tmp_path)
    destination = tmp_path / "existing"
    destination.mkdir()

    completed = subprocess.run(
        [str(SNAPSHOT), str(source), commit, str(destination)],
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    assert "destination already exists" in completed.stderr


def test_replication_and_runtime_env_preserve_trusted_external_python(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "operator.env"
    env_file.write_text("# intentionally empty\n")
    expected_commit = "a" * 40

    for replication_env in ("env_multidimensional.sh", "env_v0.sh"):
        command = f"""
set -euo pipefail
export HARNESS_PY={shlex.quote(sys.executable)}
export AAR_TRUSTED_HARNESS_PY={shlex.quote(sys.executable)}
export HARNESS_ENV={shlex.quote(str(env_file))}
export AAR_EXPECTED_COMMIT={expected_commit}
export AAR_SOURCE_SNAPSHOT={shlex.quote(str(ROOT))}
unset AAR_EXPECTED_BRANCH
source {shlex.quote(str(ROOT / 'replication' / replication_env))}
source {shlex.quote(str(ROOT / 'scripts' / 'aar_runtime_env.sh'))}
printf '%s\n' "${{AAR_REPO}}" "${{HARNESS_PY}}" \
  "${{AAR_TRUSTED_HARNESS_PY}}" "${{HARNESS_ENV}}" \
  "${{AAR_EXPECTED_BRANCH-unset}}"
printf '%s\n' "${{AAR_RESEARCH_CHAIN_ENV_ALLOWLIST[@]}}"
"${{HARNESS_PY}}" -c 'print("python-ok")'
"""
        completed = subprocess.run(
            ["bash", "-c", command],
            cwd=ROOT,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            check=True,
        )
        lines = completed.stdout.splitlines()
        assert lines[:5] == [
            str(ROOT),
            sys.executable,
            sys.executable,
            str(env_file),
            "unset",
        ]
        assert "HARNESS_PY" in lines
        assert "AAR_TRUSTED_HARNESS_PY" in lines
        assert lines[-1] == "python-ok"


def test_runtime_env_rejects_snapshot_relative_trusted_python(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot"
    (snapshot / "aar").mkdir(parents=True)
    snapshot_python = snapshot / "bin" / "python"
    snapshot_python.parent.mkdir()
    snapshot_python.write_text("#!/bin/sh\nexit 0\n")
    snapshot_python.chmod(0o700)
    command = f"""
set -euo pipefail
export REPO={shlex.quote(str(snapshot))}
export AAR_REPO={shlex.quote(str(snapshot))}
export AAR_SOURCE_SNAPSHOT={shlex.quote(str(snapshot))}
export AAR_TRUSTED_HARNESS_PY={shlex.quote(str(snapshot_python))}
export HARNESS_PY={shlex.quote(str(snapshot_python))}
source {shlex.quote(str(ROOT / 'scripts' / 'aar_runtime_env.sh'))}
"""
    completed = subprocess.run(
        ["bash", "-c", command],
        cwd=ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 2
    assert "trusted Python cannot live inside the source snapshot" in completed.stderr
