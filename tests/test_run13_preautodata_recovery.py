from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "prepare_run13_preautodata_recovery.py"


def _load_helper() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run13_recovery_test_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, str, str]:
    source_attempt = tmp_path / "synthetic-source-attempt"
    source_team = source_attempt / "aar_teams" / "synthetic-source-team"
    target_attempt = tmp_path / "synthetic-target-attempt"
    target_team = target_attempt / "aar_teams" / "synthetic-target-team"
    for directory in (
        source_team / "autodata",
        source_team / "_train",
        target_attempt / "metadata",
        target_team / "methods",
        target_team / "scores",
        target_team / "logs",
        target_team / "forum",
        target_team / "submissions",
        target_team / "_train",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    aar_commit = "a" * 40
    autodata_commit = "b" * 40
    _write_json(
        source_attempt / "metadata" / "source-snapshots.json",
        {"aar": {"commit": aar_commit}, "autodata": {"commit": autodata_commit}},
    )

    idea_name = "synthetic_safe_method"
    source_uid = "synthetic-source-idea"
    source_run = "synthetic-source-run"
    target_uid = "synthetic-trial4-idea"
    method = source_team / "methods" / idea_name / "run.py"
    method.parent.mkdir(parents=True)
    method.write_text("def main():\n    return 'synthetic'\n", encoding="utf-8")
    method_code_hash = hashlib.sha256(
        ("# ===== run.py =====\n" + method.read_text()).encode()
    ).hexdigest()
    paper = {
        field: f"synthetic {field.replace('_', ' ')}"
        for field in (
            "title",
            "abstract",
            "motivation",
            "related_work",
            "method",
            "data",
            "experimental_setup",
        )
    }
    verdict = {
        "approved": True,
        "violations": [],
        "missing_for_reproduction": [],
        "error": None,
    }
    stamp = source_team / "scores" / ".proposals" / "runs" / "source.json"
    event = source_team / "host_memory" / "synthetic-chain" / "events" / "event.json"
    evidence = source_team / "scores" / "source-evidence.json"
    _write_json(
        stamp,
        {
            "run_id": source_run,
            "idea_name": idea_name,
            "code_hash": method_code_hash,
            "paper": paper,
        },
    )
    _write_json(
        event,
        {
            "schema": "aar.chain-memory-event/v1",
            "kind": "proposal",
            "source": "proposal_decision",
            "approved": True,
            "idea_name": idea_name,
            "code_sha256": method_code_hash,
        },
    )
    _write_json(
        evidence,
        {
            "approved": True,
            "execution_ready": True,
            "journaled": True,
            "idea_name": idea_name,
            "code_hash": method_code_hash,
            "run_id": source_run,
            "paper": paper,
            "verdict": verdict,
        },
    )
    roles = {
        "method_source": method,
        "literature_research_and_proposal_stamp": stamp,
        "approved_proposal_event": event,
        "method_contract_and_approval_evidence": evidence,
    }
    manifest = {
        "schema": "aar.run13-preautodata-recovery-manifest/v1",
        "source": {
            "experiment_run_id": "run13",
            "trial_id": "trial3",
            "chain": "alpha",
            "attempt_root": str(source_attempt),
            "team_root": str(source_team),
            "aar_commit": aar_commit,
            "autodata_commit": autodata_commit,
            "source_run_id": source_run,
            "source_idea_uid": source_uid,
            "idea_name": idea_name,
            "method_code_hash": method_code_hash,
        },
        "target": {
            "experiment_run_id": "run13",
            "trial_id": "trial4",
            "chain": "alpha",
            "idea_uid": target_uid,
            "entry_boundary": "fresh_autodata_workspace_before_clarify_design",
            "require_fresh_attempt": True,
            "require_fresh_team": True,
            "require_fresh_autodata_state": True,
        },
        "artifacts": [
            {
                "role": role,
                "path": str(path),
                "sha256": f"sha256:{_sha256(path)}",
                **(
                    {
                        "required_fields": {
                            "approved": True,
                            "execution_ready": True,
                            "journaled": True,
                            "run_id": source_run,
                        }
                    }
                    if role == "method_contract_and_approval_evidence"
                    else {}
                ),
            }
            for role, path in roles.items()
        ],
        "method_contract": {"fresh_validation_required": True},
        "fresh_autodata_contract": {
            "forbidden_source_prefixes": [
                str(source_team / "autodata"),
                str(source_team / "_train"),
            ],
            "forbidden_reuse": ["autodata_state", "training_state"],
            "forbidden_native_ids": {
                "workspace": "synthetic-old-workspace",
                "execution": "synthetic-old-execution",
            },
            "required_first_native_action": "clarify_design",
        },
    }
    manifest_path = tmp_path / "operator-manifest.json"
    _write_json(manifest_path, manifest)
    os.chmod(manifest_path, 0o600)
    return manifest_path, target_attempt, target_team, target_uid, idea_name


def test_prepare_import_is_fresh_and_idempotent(tmp_path: Path, monkeypatch) -> None:
    helper = _load_helper()
    manifest, attempt, team, idea_uid, idea_name = _fixture(tmp_path)
    receipt = attempt / "metadata" / "preautodata-import-receipt.json"

    import aar.config as config

    monkeypatch.setattr(config, "IDEAS_DIR", str(team / "methods"))

    validator_python = tmp_path / "validator-venv" / "bin" / "python"
    validator_python.parent.mkdir(parents=True)
    validator_python.symlink_to(Path(sys.executable).resolve())
    validator_commands: list[list[str]] = []

    def fake_validator(command, **kwargs):
        validator_commands.append(command)
        proof = Path(command[command.index("--proof") + 1])
        method = Path(command[2])
        _write_json(
            proof,
            {
                "schema_version": 1,
                "status": "passed",
                "method_path": str(method.resolve()),
                "source_sha256": _sha256(method),
                "requirements": {
                    "run_dry_run": True,
                    "require_gemma4_targets": True,
                    "require_smoke_run": True,
                    "require_autodata_loader": True,
                },
                "errors": [],
            },
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(helper.subprocess, "run", fake_validator)
    arguments = {
        "manifest_path": manifest,
        "team_dir": team,
        "attempt_dir": attempt,
        "receipt_path": receipt,
        "repo": REPO,
        "python": validator_python,
        "chain_id": "synthetic-target-chain",
        "idea_uid": idea_uid,
    }
    first = helper.prepare_import(**arguments)
    second = helper.prepare_import(**arguments)

    assert second == first
    assert len(validator_commands) == 1
    assert Path(validator_commands[0][0]) == validator_python
    assert Path(validator_commands[0][0]).is_symlink()
    assert first["target"]["validator_python"] == str(validator_python)
    assert first["target"]["validator_python_realpath"] == str(
        Path(sys.executable).resolve()
    )
    assert first["target"]["idea_uid"] == idea_uid
    assert first["target"]["run_id"].startswith(f"{idea_uid}-")
    assert first["target"]["first_native_action"] == "clarify_design"
    assert not (team / "autodata").exists()
    assert (team / "methods" / idea_name / ".aar-method-contract.json").is_file()
    marker = json.loads(
        (team / "scores" / ".proposals" / f"{idea_uid}.json").read_text()
    )
    assert marker["execution_ready"] is True
    assert "autodata_bootstrap" not in marker
    active = "\n".join(
        path.read_text(errors="replace") for path in team.rglob("*") if path.is_file()
    )
    assert "synthetic-source-run" not in active
    assert "synthetic-old-workspace" not in active


def test_manifest_can_bind_a_fresh_trial5_target(tmp_path: Path) -> None:
    helper = _load_helper()
    manifest, _, _, _, _ = _fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["target"]["trial_id"] = "trial5"
    payload["target"]["idea_uid"] = "synthetic-trial5-idea"
    _write_json(manifest, payload)
    os.chmod(manifest, 0o600)

    verified = helper.verify_manifest(manifest, target_trial_id="trial5")

    assert verified.manifest["target"]["trial_id"] == "trial5"


def test_manifest_can_bind_a_fresh_trial6_target(tmp_path: Path) -> None:
    helper = _load_helper()
    manifest, _, _, _, _ = _fixture(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["target"]["trial_id"] = "trial6"
    payload["target"]["idea_uid"] = "synthetic-trial6-idea"
    _write_json(manifest, payload)
    os.chmod(manifest, 0o600)

    verified = helper.verify_manifest(manifest, target_trial_id="trial6")

    assert verified.manifest["target"]["trial_id"] == "trial6"


def test_manifest_can_bind_a_fresh_trial7_target(tmp_path: Path) -> None:
    helper = _load_helper()
    manifest, *_ = _fixture(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["target"]["trial_id"] = "trial7"
    payload["target"]["idea_uid"] = "synthetic-trial7-idea"
    manifest.write_text(json.dumps(payload))

    verified = helper.verify_manifest(manifest, target_trial_id="trial7")

    assert verified.manifest["target"]["trial_id"] == "trial7"


def test_manifest_target_must_match_requested_trial(tmp_path: Path) -> None:
    helper = _load_helper()
    manifest, _, _, _, _ = _fixture(tmp_path)

    with pytest.raises(helper.RecoveryImportError, match="trial5"):
        helper.verify_manifest(manifest, target_trial_id="trial5")


def test_manifest_hash_drift_is_rejected(tmp_path: Path) -> None:
    helper = _load_helper()
    manifest, _, _, _, _ = _fixture(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["artifacts"][0]["sha256"] = "sha256:" + "0" * 64
    _write_json(manifest, payload)
    os.chmod(manifest, 0o600)

    with pytest.raises(helper.RecoveryImportError, match="hash mismatch"):
        helper.verify_manifest(manifest)


def test_partial_import_without_receipt_fails_closed(
    tmp_path: Path, monkeypatch
) -> None:
    helper = _load_helper()
    manifest, attempt, team, idea_uid, idea_name = _fixture(tmp_path)
    (team / "methods" / idea_name).mkdir(parents=True)

    with pytest.raises(helper.RecoveryImportError, match="partial pre-AutoData"):
        helper.prepare_import(
            manifest_path=manifest,
            team_dir=team,
            attempt_dir=attempt,
            receipt_path=attempt / "metadata" / "preautodata-import-receipt.json",
            repo=REPO,
            python=Path(sys.executable),
            chain_id="synthetic-target-chain",
            idea_uid=idea_uid,
        )


def test_manifest_is_not_in_research_environment_allowlist() -> None:
    runtime = (REPO / "scripts" / "aar_runtime_env.sh").read_text()
    preserve = runtime.split("_AAR_PRESERVE=(", 1)[1].split("\n)", 1)[0]
    assert "AAR_RUN13_PREAUTODATA_RECOVERY_MANIFEST" not in preserve
    assert "AAR_AUTODATA_CLARIFY_COORDINATOR" in preserve
    assert "AAR_AUTODATA_PIPELINE_COORDINATOR" in preserve
    assert "AAR_AUTODATA_MUTATION_COORDINATOR" in preserve
    assert "AAR_AUTODATA_TRAINING_SMOKE_COORDINATOR" in preserve
    assert "AAR_AUTODATA_SEMANTIC_WORKER" in preserve
