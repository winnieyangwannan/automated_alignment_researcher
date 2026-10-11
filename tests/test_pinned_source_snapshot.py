from __future__ import annotations

import subprocess
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
