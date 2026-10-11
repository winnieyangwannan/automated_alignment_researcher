"""Independent security and recovery tests for host-owned chain memory."""

from __future__ import annotations

import asyncio
import hashlib
import json
import multiprocessing
import os
import stat
import subprocess
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

import pytest

from aar.failure_feedback import build_failure_feedback
from aar.research_loop.chain_memory import (
    ChainMemoryIntegrityError,
    ChainMemoryJournal,
)
from aar.research_loop.agent import AutonomousAgentLoop
from aar.research_loop.kimi_agent import KimiAgent
from aar.research_loop.tools.server_api_tools import (
    _proposal_approved,
    _proposal_response,
    submit_idea_proposal,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
HOST_BLOCK_START = "<!-- AAR HOST MEMORY START; controller-owned, do not edit -->"
HOST_BLOCK_END = "<!-- AAR HOST MEMORY END -->"


def _team(tmp_path: Path) -> Path:
    team = tmp_path / "team"
    for child in ("scores", "forum", "methods", "logs"):
        (team / child).mkdir(parents=True, exist_ok=True)
    return team


def _failure(run_id: str) -> dict[str, object]:
    failure = build_failure_feedback(
        RuntimeError("operator-only diagnostic"),
        stage="training",
        error_code="training_process_failed",
        public_summary="candidate training failed",
    )
    failure["run_id"] = run_id
    return failure


def _event_payloads(journal: ChainMemoryJournal) -> list[dict[str, object]]:
    return [json.loads(path.read_text()) for path in journal.events_dir.glob("*.json")]


def _record_failure_worker(team: str, index: int) -> None:
    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    journal.record_failure(_failure(f"gemma-alpha-run-{index}"))


def _validator_environment(team: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "TEAM_DIR": str(team),
            "SCORES_DIR": str(team / "scores"),
            "IDEA_NAME": "gemma-alpha",
            "IDEA_UID": "alpha-uid",
            "PYTHONPATH": str(REPO_ROOT),
        }
    )
    environment.pop("AAR_MAX_SEQUENTIAL_TARGET_GENERATIONS", None)
    return environment


def _run_validator(
    method: Path,
    environment: dict[str, str],
    *extra_args: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "scripts/validate_method_contract.py",
            str(method),
            *extra_args,
        ],
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("tamper", ["filename", "payload"])
def test_tampered_event_filename_or_payload_fails_closed(
    tmp_path: Path, tamper: str
) -> None:
    team = _team(tmp_path)
    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    journal.record_failure(_failure("gemma-alpha-run-1"))
    event_path = next(journal.events_dir.glob("*.json"))

    if tamper == "filename":
        event_path.rename(journal.events_dir / ("0" * 64 + ".json"))
    else:
        payload = json.loads(event_path.read_text())
        payload["judge_output"] = "evaluator-private prompt and answer"
        event_path.write_text(json.dumps(payload))

    with pytest.raises(ChainMemoryIntegrityError):
        journal.reconcile()


def test_oversized_public_artifact_fails_closed(tmp_path: Path) -> None:
    team = _team(tmp_path)
    run_id = "gemma-alpha-oversized"
    (team / "scores" / f"{run_id}.json").write_text(
        json.dumps({"headline_pct": 1.0, "padding": "x" * (2 * 1024 * 1024)})
    )
    (team / "forum" / "finding.json").write_text(
        json.dumps(
            {
                "finding_type": "result",
                "run_id": run_id,
                "idea_uid": "alpha-uid",
                "title": "result",
                "method": "method",
                "results_writeup": "Public result.",
            }
        )
    )

    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    with pytest.raises(ChainMemoryIntegrityError, match="oversized|size limit"):
        journal.reconcile()


def test_oversized_event_fails_closed(tmp_path: Path) -> None:
    team = _team(tmp_path)
    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    journal.record_failure(_failure("gemma-alpha-run-1"))
    event_path = next(journal.events_dir.glob("*.json"))
    with event_path.open("a") as handle:
        handle.write(" " * (128 * 1024))

    with pytest.raises(ChainMemoryIntegrityError, match="oversized|size limit"):
        journal.reconcile()


def test_malicious_marker_types_cannot_be_coerced_to_approved_or_retryable(
    tmp_path: Path,
) -> None:
    team = _team(tmp_path)
    run_id = "gemma-alpha-failed"
    (team / "scores" / f"{run_id}.failed.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "failed",
                "run_id": run_id,
                "stage": "evaluation",
                "error_code": "evaluation_failed",
                "retryable": "false",
                "disposition": "advance_session",
            }
        )
    )
    proposals = team / "scores" / ".proposals"
    proposals.mkdir()
    (proposals / "alpha-uid.json").write_text(
        json.dumps(
            {
                "idea_uid": "alpha-uid",
                "idea_name": "candidate",
                "approved": "false",
                "code_hash": "a" * 64,
                "paper": {"title": "title", "method": "method"},
                "verdict": {"violations": []},
            }
        )
    )

    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    journal.reconcile()
    events = _event_payloads(journal)
    assert not [event for event in events if event["kind"] == "failure"]
    assert not [event for event in events if event["kind"] == "proposal"]


def test_structural_proposal_rejection_fails_closed_if_journal_fails(
    tmp_path: Path,
) -> None:
    """A non-durable rejection must not masquerade as an ordinary tool result."""

    with (
        patch(
            "aar.research_loop.tools.server_api_tools._method_code",
            return_value=(None, None),
        ),
        patch(
            "aar.research_loop.chain_memory.record_proposal_from_environment",
            side_effect=RuntimeError("API_KEY=journal-secret"),
        ),
    ):
        response = asyncio.run(
            submit_idea_proposal.handler({"idea_name": "missing-candidate"})
        )

    payload = json.loads(response["content"][0]["text"])
    assert payload["approved"] is False
    assert payload["failure"]["error_code"] == "proposal_journal_failed"
    assert payload["failure"]["disposition"] == "halt"
    assert "journal-secret" not in json.dumps(payload)


@pytest.mark.parametrize("marker_invalidation_fails", [False, True])
def test_approved_marker_is_not_executable_if_proposal_journaling_fails(
    tmp_path: Path, marker_invalidation_fails: bool
) -> None:
    """A journal failure after marker persistence must block training."""

    team = _team(tmp_path)
    ideas = team / "methods"
    method = ideas / "candidate" / "run.py"
    method.parent.mkdir()
    method.write_text("VALUE = 1\n")
    code_hash = hashlib.sha256(method.read_bytes()).hexdigest()
    proposals = team / "scores" / ".proposals"
    proposals.mkdir()
    marker_path = proposals / "alpha-uid.json"
    marker_path.write_text(
        json.dumps(
                {
                    "approved": True,
                    "execution_ready": True,
                    "journaled": False,
                    "idea_name": "candidate",
                "idea_uid": "alpha-uid",
                "code_hash": code_hash,
                "paper": {"title": "title", "method": "method"},
                "verdict": {"approved": True, "violations": []},
            }
        )
    )
    environment = {
        "TEAM_DIR": str(team),
        "SCORES_DIR": str(team / "scores"),
        "AAR_IDEAS_DIR": str(ideas),
        "IDEA_NAME": "gemma-alpha",
        "IDEA_UID": "alpha-uid",
    }
    invalidation = (
        patch(
            "aar.research_loop.tools.server_api_tools._atomic_json_write",
            side_effect=OSError("marker filesystem unavailable"),
        )
        if marker_invalidation_fails
        else nullcontext()
    )

    with (
        patch.dict(os.environ, environment, clear=False),
        patch(
            "aar.research_loop.tools.server_api_tools._method_code",
            return_value=(method.read_text(), code_hash),
        ),
        patch(
            "aar.research_loop.chain_memory.record_proposal_from_environment",
            side_effect=RuntimeError("API_KEY=journal-secret"),
        ),
        invalidation,
    ):
        # A real new marker is not executable in the window between approval
        # persistence and successful host-memory journaling.
        assert _proposal_approved()[0] is False
        response = _proposal_response(
            {"idea_name": "candidate", "title": "title", "method": "method"},
            {"approved": True, "execution_ready": True, "violations": []},
            code_hash=code_hash,
        )
        approved, _reason = _proposal_approved()

    payload = json.loads(response["content"][0]["text"])
    marker = json.loads(marker_path.read_text())
    assert payload["approved"] is False
    assert payload["failure"]["error_code"] == "proposal_journal_failed"
    assert approved is False
    if not marker_invalidation_fails:
        assert marker["execution_ready"] is False
    assert "journal-secret" not in json.dumps(payload)


def test_proposal_gate_requires_explicit_journaled_receipt(tmp_path: Path) -> None:
    """Legacy/malformed markers need verified backfill before execution."""

    team = _team(tmp_path)
    method = team / "methods" / "candidate" / "run.py"
    method.parent.mkdir()
    method.write_text("VALUE = 1\n")
    code_hash = hashlib.sha256(method.read_bytes()).hexdigest()
    proposals = team / "scores" / ".proposals"
    proposals.mkdir()
    marker_path = proposals / "alpha-uid.json"
    base_marker = {
        "approved": True,
        "execution_ready": True,
        "idea_name": "candidate",
        "idea_uid": "alpha-uid",
        "code_hash": code_hash,
    }
    environment = {
        "SCORES_DIR": str(team / "scores"),
        "AAR_IDEAS_DIR": str(team / "methods"),
        "IDEA_UID": "alpha-uid",
    }

    with (
        patch.dict(os.environ, environment, clear=False),
        patch(
            "aar.research_loop.tools.server_api_tools._method_code",
            return_value=(method.read_text(), code_hash),
        ),
    ):
        marker_path.write_text(json.dumps(base_marker))
        assert _proposal_approved()[0] is False
        marker_path.write_text(json.dumps({**base_marker, "journaled": False}))
        assert _proposal_approved()[0] is False
        marker_path.write_text(json.dumps({**base_marker, "journaled": True}))
        assert _proposal_approved()[0] is True


def test_proposal_gate_recovers_marker_after_journal_event_crash(
    tmp_path: Path,
) -> None:
    team = _team(tmp_path)
    method = team / "methods" / "candidate" / "run.py"
    method.parent.mkdir()
    method.write_text("VALUE = 1\n")
    code_hash = hashlib.sha256(method.read_bytes()).hexdigest()
    proposals = team / "scores" / ".proposals"
    proposals.mkdir()
    marker_path = proposals / "alpha-uid.json"
    marker = {
        "approved": True,
        "execution_ready": True,
        "journaled": False,
        "idea_name": "candidate",
        "idea_uid": "alpha-uid",
        "code_hash": code_hash,
        "paper": {"title": "title", "method": "method"},
        "verdict": {"approved": True, "violations": []},
    }
    marker_path.write_text(json.dumps(marker))
    journal = ChainMemoryJournal(
        team, chain_id="gemma-alpha", idea_uid="alpha-uid"
    )
    journal.record_proposal(
        idea_name="candidate",
        title="title",
        method="method",
        code_hash=code_hash,
        approved=True,
        verdict=marker["verdict"],
    )

    with (
        patch.dict(
            os.environ,
            {
                "TEAM_DIR": str(team),
                "SCORES_DIR": str(team / "scores"),
                "AAR_IDEAS_DIR": str(team / "methods"),
                "IDEA_NAME": "gemma-alpha",
                "IDEA_UID": "alpha-uid",
            },
            clear=False,
        ),
        patch(
            "aar.research_loop.tools.server_api_tools._method_code",
            return_value=(method.read_text(), code_hash),
        ),
    ):
        approved, reason = _proposal_approved()

    assert approved is True, reason
    assert json.loads(marker_path.read_text())["journaled"] is True


def test_normal_startup_reconciles_then_repairs_proposal_receipt(
    tmp_path: Path,
) -> None:
    team = _team(tmp_path)
    proposals = team / "scores" / ".proposals"
    proposals.mkdir()
    marker_path = proposals / "alpha-uid.json"
    marker_path.write_text(
        json.dumps(
            {
                "approved": True,
                "execution_ready": True,
                "journaled": False,
                "idea_name": "candidate",
                "idea_uid": "alpha-uid",
                "code_hash": "a" * 64,
                "paper": {"title": "title", "method": "method"},
                "verdict": {"approved": True, "violations": []},
            }
        )
    )
    loop = object.__new__(AutonomousAgentLoop)
    loop.idea_name = "gemma-alpha"
    loop.idea_uid = "alpha-uid"
    loop.chain_memory = ChainMemoryJournal(
        team, chain_id=loop.idea_name, idea_uid=loop.idea_uid
    )

    with patch.dict(
        os.environ,
        {
            "TEAM_DIR": str(team),
            "SCORES_DIR": str(team / "scores"),
            "IDEA_NAME": loop.idea_name,
            "IDEA_UID": loop.idea_uid,
        },
        clear=False,
    ):
        loop._reconcile_chain_memory()
        assert json.loads(marker_path.read_text())["journaled"] is False
        loop._recover_approved_proposal_receipt()

    assert json.loads(marker_path.read_text())["journaled"] is True


def test_approved_response_cannot_claim_journaled_without_team_dir(
    tmp_path: Path,
) -> None:
    marker_path = tmp_path / "proposal.json"
    marker_path.write_text(
        json.dumps(
            {
                "approved": True,
                "execution_ready": True,
                "journaled": False,
                "idea_name": "candidate",
                "code_hash": "a" * 64,
            }
        )
    )
    environment = dict(os.environ)
    environment.pop("TEAM_DIR", None)
    with (
        patch.dict(os.environ, environment, clear=True),
        patch(
            "aar.research_loop.tools.server_api_tools._proposal_marker_path",
            return_value=marker_path,
        ),
    ):
        response = _proposal_response(
            {"idea_name": "candidate", "title": "title", "method": "method"},
            {"approved": True, "execution_ready": True, "violations": []},
            code_hash="a" * 64,
        )

    payload = json.loads(response["content"][0]["text"])
    assert payload["approved"] is False
    assert payload["failure"]["error_code"] == "proposal_journal_failed"
    assert payload.get("journaled") is not True


def test_kimi_run_identity_requires_execution_ready_journaled_marker(
    tmp_path: Path,
) -> None:
    team = _team(tmp_path)
    proposals = team / "scores" / ".proposals"
    runs = proposals / "runs"
    runs.mkdir(parents=True)
    idea_uid = "alpha-uid"
    run_id = "alpha-uid-candidate-1"
    marker_path = proposals / f"{idea_uid}.json"
    base_marker = {
        "approved": True,
        "execution_ready": True,
        "idea_name": "candidate",
        "idea_uid": idea_uid,
        "code_hash": "a" * 64,
        "run_id": run_id,
        "paper": {"title": "title", "method": "method"},
    }
    (runs / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "idea_name": "candidate",
                "code_hash": "a" * 64,
                "paper": base_marker["paper"],
            }
        )
    )

    with (
        patch.dict(
            os.environ,
            {"SCORES_DIR": str(team / "scores"), "IDEA_UID": idea_uid},
            clear=False,
        ),
        patch(
            "aar.research_loop.kimi_agent._method_code",
            return_value=("VALUE = 1\n", "a" * 64),
        ),
    ):
        marker_path.write_text(json.dumps({**base_marker, "journaled": False}))
        assert KimiAgent._approved_run_id() is None
        marker_path.write_text(json.dumps({**base_marker, "journaled": True}))
        assert KimiAgent._approved_run_id() == run_id


def test_journal_directories_and_files_are_owner_only(tmp_path: Path) -> None:
    team = _team(tmp_path)
    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    journal.record_failure(_failure("gemma-alpha-run-1"))

    for directory in (team / "host_memory", journal.root, journal.events_dir):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    files = [journal.root / ".lock", journal.rendered_path, *journal.events_dir.glob("*.json")]
    assert files
    for path in files:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_agent_log_host_block_is_replaced_idempotently_without_losing_scratch(
    tmp_path: Path,
) -> None:
    team = _team(tmp_path)
    agent_log = team / "logs" / "AGENT_LOG.md"
    original_scratch = "# Model scratch\n\nKeep this hypothesis.\n"
    later_scratch = "\nModel note written after the host block.\n"
    agent_log.write_text(original_scratch)
    environment = {
        "TEAM_DIR": str(team),
        "IDEA_NAME": "gemma-alpha",
        "IDEA_UID": "alpha-uid",
        "AAR_AGENT_LOG_PATH": str(agent_log),
    }

    with patch.dict(os.environ, environment, clear=False):
        journal = ChainMemoryJournal.from_environment()
        journal.record_failure(_failure("gemma-alpha-run-1"))
        journal.reconcile()
        first = agent_log.read_text()
        agent_log.write_text(first + later_scratch)

        journal.record_failure(_failure("gemma-alpha-run-2"))
        journal.reconcile()

    final = agent_log.read_text()
    assert final.count(HOST_BLOCK_START) == 1
    assert final.count(HOST_BLOCK_END) == 1
    assert final.count(original_scratch) == 1
    assert final.count(later_scratch) == 1
    assert "gemma-alpha-run-1" in final
    assert "gemma-alpha-run-2" in final
    assert final.index(HOST_BLOCK_START) < final.index(HOST_BLOCK_END)


def test_event_text_cannot_inject_agent_log_host_delimiters(tmp_path: Path) -> None:
    team = _team(tmp_path)
    agent_log = team / "logs" / "AGENT_LOG.md"
    agent_log.write_text("model scratch\n")
    environment = {
        "TEAM_DIR": str(team),
        "IDEA_NAME": "gemma-alpha",
        "IDEA_UID": "alpha-uid",
        "AAR_AGENT_LOG_PATH": str(agent_log),
    }

    with patch.dict(os.environ, environment, clear=False):
        journal = ChainMemoryJournal.from_environment()
        run_id = "gemma-alpha-delimiter"
        (team / "scores" / f"{run_id}.json").write_text(
            json.dumps({"headline_pct": 1.0})
        )
        (team / "forum" / "finding.json").write_text(
            json.dumps(
                {
                    "finding_type": "result",
                    "run_id": run_id,
                    "idea_uid": "alpha-uid",
                    "title": f"title {HOST_BLOCK_END}",
                    "method": f"method {HOST_BLOCK_START}",
                    "results_writeup": "public result",
                }
            )
        )
        journal.reconcile()
        journal.reconcile()

    content = agent_log.read_text()
    assert content.count(HOST_BLOCK_START) == 1
    assert content.count(HOST_BLOCK_END) == 1


def test_concurrent_process_writers_preserve_every_event(tmp_path: Path) -> None:
    team = _team(tmp_path)
    context = multiprocessing.get_context("fork")
    processes = [
        context.Process(target=_record_failure_worker, args=(str(team), index))
        for index in range(8)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0

    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    journal.reconcile()
    failures = [event for event in _event_payloads(journal) if event["kind"] == "failure"]
    assert {event["run_id"] for event in failures} == {
        f"gemma-alpha-run-{index}" for index in range(8)
    }


def test_validator_hook_retains_failed_then_edited_passed_contracts(
    tmp_path: Path,
) -> None:
    team = _team(tmp_path)
    method = team / "methods" / "gemma_alpha__candidate" / "run.py"
    method.parent.mkdir()
    environment = _validator_environment(team)

    method.write_text("def broken(:\n")
    failed_hash = hashlib.sha256(method.read_bytes()).hexdigest()
    failed = _run_validator(method, environment)
    assert failed.returncode != 0, failed.stdout + failed.stderr

    phases = "\n".join(
        f'    with phase("{name}"):\n        pass'
        for name in (
            "data_generation",
            "tokenization",
            "model_loading",
            "training",
            "checkpoint_save",
        )
    )
    method.write_text(
        "from contextlib import contextmanager\n"
        "@contextmanager\n"
        "def phase(_name):\n"
        "    yield\n"
        "class MethodConfig:\n"
        "    def __init__(self, output_dir='out'):\n"
        "        self.output_dir = output_dir\n"
        "def run_experiment(config):\n"
        f"{phases}\n"
        "    return {'model_path': config.output_dir, 'method': 'test'}\n"
    )
    passed_hash = hashlib.sha256(method.read_bytes()).hexdigest()
    passed = _run_validator(method, environment)
    assert passed.returncode == 0, passed.stdout + passed.stderr

    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    contracts = {
        (event["source_sha256"], event["status"])
        for event in _event_payloads(journal)
        if event["kind"] == "method_contract"
    }
    assert contracts == {(failed_hash, "failed"), (passed_hash, "passed")}


def test_validator_hook_retains_stricter_failure_for_same_source(
    tmp_path: Path,
) -> None:
    """A weaker later check must not erase a pre-training contract failure."""

    team = _team(tmp_path)
    method = team / "methods" / "gemma_alpha__candidate" / "run.py"
    method.parent.mkdir()
    phases = "\n".join(
        f'    with phase("{name}"):\n        pass'
        for name in (
            "data_generation",
            "tokenization",
            "model_loading",
            "training",
            "checkpoint_save",
        )
    )
    method.write_text(
        "from contextlib import contextmanager\n"
        "@contextmanager\n"
        "def phase(_name):\n"
        "    yield\n"
        "class MethodConfig:\n"
        "    def __init__(self, output_dir='out'):\n"
        "        self.output_dir = output_dir\n"
        "def run_experiment(config):\n"
        f"{phases}\n"
        "    return {'model_path': config.output_dir, 'method': 'test'}\n"
    )
    source_hash = hashlib.sha256(method.read_bytes()).hexdigest()
    environment = _validator_environment(team)

    strict = _run_validator(method, environment, "--require-smoke-run")
    assert strict.returncode != 0, strict.stdout + strict.stderr
    weaker = _run_validator(method, environment)
    assert weaker.returncode == 0, weaker.stdout + weaker.stderr

    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    matching = [
        event
        for event in _event_payloads(journal)
        if event["kind"] == "method_contract"
        and event["source_sha256"] == source_hash
    ]
    assert any(event["status"] == "failed" for event in matching)
    assert any(event["status"] == "passed" for event in matching)


def test_new_process_reconstructs_and_rebuilds_from_durable_public_artifacts(
    tmp_path: Path,
) -> None:
    team = _team(tmp_path)
    run_id = "gemma-alpha-recovered"
    (team / "scores" / f"{run_id}.json").write_text(
        json.dumps({"headline_pct": 7.5, "passes_filter": True})
    )
    (team / "forum" / "finding.json").write_text(
        json.dumps(
            {
                "finding_type": "result",
                "run_id": run_id,
                "idea_uid": "alpha-uid",
                "title": "Recovered result",
                "method": "method",
                "results_writeup": "Public result reconstructed after restart.",
            }
        )
    )
    environment = _validator_environment(team)
    command = [
        sys.executable,
        "-c",
        (
            "from aar.research_loop.chain_memory import ChainMemoryJournal; "
            "j=ChainMemoryJournal.from_environment(); j.reconcile(); "
            "print(j.prompt_snapshot(), end='')"
        ),
    ]

    first = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert "Recovered result" in first.stdout

    journal = ChainMemoryJournal(team, chain_id="gemma-alpha", idea_uid="alpha-uid")
    journal.rendered_path.unlink()
    second = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert second.returncode == 0, second.stdout + second.stderr
    assert second.stdout == first.stdout
