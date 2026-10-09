from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from aar.champion import (
    ChampionExportError,
    export_champion,
    method_code_hash,
    select_champion,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _make_model(team: Path, run_id: str, *, valid: bool = True) -> Path:
    model = team / "submissions" / run_id / "model"
    model.mkdir(parents=True)
    _write_json(model / "config.json", {"_name_or_path": "org/base-model"})
    (model / "model.safetensors").write_bytes(b"model weights")
    _write_json(model / "tokenizer_config.json", {"model_max_length": 1024})
    if valid:
        _write_json(model / "tokenizer.json", {"version": "1.0"})
    return model


def _make_method_and_proposal(
    team: Path,
    run_id: str,
    idea_name: str,
    *,
    proposal_ts: float,
) -> None:
    method = team / "methods" / idea_name
    method.mkdir(parents=True)
    (method / "__init__.py").write_text("", encoding="utf-8")
    (method / "run.py").write_text(
        "def run_experiment(config):\n"
        "    return {'model_path': config.output_dir, 'method': 'test'}\n",
        encoding="utf-8",
    )
    code_hash = method_code_hash(method)
    assert code_hash
    paper = {
        "title": f"Method {idea_name}",
        "abstract": "A sufficiently descriptive abstract for the exported method.",
        "motivation": "Improve all target dimensions without capability loss.",
        "related_work": "Prior work provides the foundations for this method.",
        "method": "Train a low-rank adapter with a balanced objective.",
        "data": "Programmatically generated, benchmark-disjoint examples.",
        "experimental_setup": "One epoch of PEFT training on the target model.",
    }
    _write_json(
        team / "scores" / ".proposals" / "runs" / f"{run_id}.json",
        {
            "run_id": run_id,
            "idea_name": idea_name,
            "proposal_ts": proposal_ts,
            "code_hash": code_hash,
            "paper": paper,
        },
    )


def _score(headline: float, *, passes: bool = True, backend: str = "vllm") -> dict:
    return {
        "suite": "joint_suite",
        "model": "/temporary/merged/checkpoint",
        "inference_backend": backend,
        "headline_pct": headline,
        "passes_filter": passes,
        "passes_regression": passes,
        "aggregation": {"mode": "coverage_weighted_geometric_mean"},
        "closed_pct": {"bench": headline},
        "per_benchmark": {
            "bench": {
                "mean": 0.6,
                "ci_low": 0.5,
                "ci_high": 0.7,
                "n": 10,
                "role": "safety",
                "baseline": 0.5,
                "optimum": 1.0,
            }
        },
    }


def _make_candidate(
    team: Path,
    run_id: str,
    headline: float,
    *,
    passes: bool = True,
    valid_model: bool = True,
    backend: str = "vllm",
    proposal_ts: float = 1.0,
) -> None:
    (team / "scores").mkdir(parents=True, exist_ok=True)
    _write_json(
        team / "scores" / f"{run_id}.json",
        _score(headline, passes=passes, backend=backend),
    )
    _make_method_and_proposal(
        team,
        run_id,
        f"idea_{run_id}",
        proposal_ts=proposal_ts,
    )
    _make_model(team, run_id, valid=valid_model)


def test_export_selects_highest_valid_result_and_packages_provenance(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "attempt-1"
    team = attempt / "aar_teams" / "team-1"
    _make_candidate(team, "invalid-high", 99.0, passes=False)
    _make_candidate(team, "winner", 12.5, proposal_ts=2.0)
    _make_candidate(team, "runner-up", 8.0, proposal_ts=1.0)
    _write_json(
        team / "forum" / "finding.json",
        {
            "id": "finding-1",
            "finding_type": "result",
            "run_id": "winner",
            "idea_name": "idea_winner",
            "results_writeup": (
                "The method improved the optimized suite without a capability regression."
            ),
        },
    )
    metadata = attempt / "metadata" / "submission.txt"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "git_commit=abc123\nresearch_backend=kimi\nsecret=do-not-copy\n",
        encoding="utf-8",
    )

    output = attempt / "champion"
    manifest = export_champion(
        team,
        output,
        expected_suite="joint_suite",
        expected_inference_backend="vllm",
        required_artifact_type="full_model",
    )

    assert manifest["selected"]["run_id"] == "winner"
    assert manifest["selected"]["headline_pct"] == 12.5
    assert manifest["selected"]["base_model"] == "org/base-model"
    assert manifest["run_metadata"] == {
        "git_commit": "abc123",
        "research_backend": "kimi",
    }
    assert (output / "model/model.safetensors").read_bytes() == b"model weights"
    assert (output / "method/run.py").is_file()
    assert (output / "finding.json").is_file()
    assert "Method idea_winner" in (output / "method_card.md").read_text()

    checksums = json.loads((output / "checksums.json").read_text())
    assert "champion.json" in checksums
    assert "model/model.safetensors" in checksums
    for relative, expected in checksums.items():
        payload = (output / relative).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == expected["sha256"]
        assert len(payload) == expected["size_bytes"]


def test_selection_falls_back_when_higher_scoring_artifact_is_invalid(
    tmp_path: Path,
) -> None:
    team = tmp_path / "team"
    _make_candidate(team, "broken", 20.0, valid_model=False)
    _make_candidate(team, "working", 10.0)

    champion, candidates = select_champion(team)

    assert champion.run_id == "working"
    broken = next(candidate for candidate in candidates if candidate.run_id == "broken")
    assert any("model validation failed" in reason for reason in broken.reasons)


def test_selection_refuses_mixed_evaluation_protocols(tmp_path: Path) -> None:
    team = tmp_path / "team"
    _make_candidate(team, "vllm", 20.0, backend="vllm")
    _make_candidate(team, "transformers", 10.0, backend="transformers")

    with pytest.raises(ChampionExportError, match="different suites"):
        select_champion(team)


def test_selection_rejects_method_that_no_longer_matches_approval(
    tmp_path: Path,
) -> None:
    team = tmp_path / "team"
    _make_candidate(team, "changed", 20.0)
    (team / "methods" / "idea_changed" / "run.py").write_text(
        "# changed after approval\n", encoding="utf-8"
    )

    with pytest.raises(ChampionExportError, match="no metadata-valid candidate"):
        select_champion(team)
