from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from aar.slurm_session_recovery import prepare_intent, transition_intent


ROOT = Path(__file__).resolve().parents[1]
SUBMITTER = ROOT / "scripts" / "submit_train_job.sh"


def _environment(fake_bin: Path, team: Path) -> dict[str, str]:
    return {
        **os.environ,
        "AAR_REPO": str(ROOT),
        "AAR_RUNTIME_ENV_DISABLE_FILE": "1",
        "HARNESS_PY": sys.executable,
        "TEAM_DIR": str(team),
        "AAR_SLURM_ACCOUNT": "ram",
        "AAR_SLURM_PARTITION": "g3",
        "AAR_TRAIN_QOS": "g3_ram_high",
        "AAR_REQUIRE_TRAIN_RECEIPT": "1",
        "AAR_MAX_CONCURRENT_TRAIN_JOBS": "2",
        "PATH": f"{fake_bin}:/usr/bin:/bin",
    }


def test_training_receipt_is_published_after_atomic_lane_state(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    team = tmp_path / "team"
    moves = tmp_path / "moves"
    calls = tmp_path / "sbatch-calls"
    (fake_bin / "sbatch").write_text(
        f"#!/bin/bash\nprintf 'call\\n' >> {calls}\nprintf '12345;cluster\\n'\n",
        encoding="utf-8",
    )
    (fake_bin / "mv").write_text(
        f"#!/bin/bash\nprintf '%s\\n' \"${{@: -1}}\" >> {moves}\n"
        "exec /usr/bin/mv \"$@\"\n",
        encoding="utf-8",
    )
    for name in ("sbatch", "mv"):
        (fake_bin / name).chmod(0o755)

    completed = subprocess.run(
        ["bash", str(SUBMITTER), "idea", "run-1"],
        check=True,
        capture_output=True,
        text=True,
        env=_environment(fake_bin, team),
    )

    assert completed.stdout.strip() == "12345"
    assert calls.read_text(encoding="utf-8").splitlines() == ["call"]
    assert (team / ".train_dependency_lanes").read_text().splitlines() == [
        "12345",
        "",
    ]
    assert (team / ".train_dependency_lanes.cursor").read_text() == "1\n"
    receipt = team / ".train_submissions" / "run-1.env"
    assert receipt.read_text() == "run_id=run-1\njob_id=12345\n"
    destinations = moves.read_text(encoding="utf-8").splitlines()
    assert destinations.index(str(team / ".train_dependency_lanes")) < (
        destinations.index(str(receipt))
    )
    assert destinations.index(str(team / ".train_dependency_lanes.cursor")) < (
        destinations.index(str(receipt))
    )
    intent = json.loads(
        (team / ".train_submissions" / "run-1.intent.json").read_text()
    )
    assert intent["status"] == "registered"
    assert intent["job_id"] == "12345"


def test_submitting_intent_reconciles_scheduler_job_without_duplicate_sbatch(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    team = tmp_path / "team"
    receipt_dir = team / ".train_submissions"
    receipt_dir.mkdir(parents=True)
    key = "team:run-1"
    digest = hashlib.sha256(key.encode()).hexdigest()[:24]
    comment = f"aar-train:{digest}"
    intent_path = receipt_dir / "run-1.intent.json"
    prepare_intent(intent_path, key=key, comment=comment)
    transition_intent(intent_path, status="submitting")

    called = tmp_path / "sbatch-called"
    (fake_bin / "sbatch").write_text(
        f"#!/bin/bash\ntouch {called}\nprintf '99999\\n'\n", encoding="utf-8"
    )
    (fake_bin / "squeue").write_text(
        f"#!/bin/bash\nprintf '24680|{comment}\\n'\n", encoding="utf-8"
    )
    (fake_bin / "sacct").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    for name in ("sbatch", "squeue", "sacct"):
        (fake_bin / name).chmod(0o755)

    completed = subprocess.run(
        ["bash", str(SUBMITTER), "idea", "run-1"],
        check=True,
        capture_output=True,
        text=True,
        env=_environment(fake_bin, team),
    )

    assert completed.stdout.strip() == "24680"
    assert not called.exists()
    assert (receipt_dir / "run-1.env").read_text() == (
        "run_id=run-1\njob_id=24680\n"
    )
    assert (team / ".train_dependency_lanes").read_text().splitlines() == [
        "24680",
        "",
    ]
    intent = json.loads(intent_path.read_text())
    assert intent["status"] == "registered"
    assert intent["job_id"] == "24680"
