from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import types
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest

from competition.export_aar_spipes import (
    CompetitionExportError,
    _parse_bool,
    _remote_path,
    method_code_hash,
    model_slug,
    render_job_script,
    select_top_candidates,
    upload_bundles,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _make_candidate(team: Path, run_id: str, headline: float, proposal_ts: float) -> Path:
    method = team / "methods" / f"idea_{run_id}"
    method.mkdir(parents=True)
    (method / "run.py").write_text("def run_experiment(config):\n    return {}\n", encoding="utf-8")
    code_hash = method_code_hash(method)
    assert code_hash
    _write_json(
        team / "scores" / ".proposals" / "runs" / f"{run_id}.json",
        {
            "run_id": run_id,
            "idea_name": f"idea_{run_id}",
            "proposal_ts": proposal_ts,
            "code_hash": code_hash,
            "paper": {"title": run_id, "abstract": "abstract", "method": "method", "data": "data"},
        },
    )
    _write_json(
        team / "scores" / f"{run_id}.json",
        {
            "suite": "joint",
            "inference_backend": "vllm",
            "headline_pct": headline,
            "passes_filter": True,
            "passes_regression": True,
            "aggregation": {"mode": "geomean"},
            "per_benchmark": {
                "bench": {"role": "safety", "baseline": 0.2, "optimum": 1.0, "floor": 0.0}
            },
        },
    )
    _write_json(
        team / "forum" / f"{run_id}.json",
        {"finding_type": "result", "run_id": run_id, "results_writeup": "result"},
    )
    model = team / "submissions" / run_id / "model"
    model.mkdir(parents=True)
    _write_json(model / "adapter_config.json", {"base_model_name_or_path": "org/base"})
    _write_json(model / "tokenizer_config.json", {})
    (model / "tokenizer.json").write_text("{}", encoding="utf-8")
    (model / "adapter_model.safetensors").write_bytes(b"weights")
    return model


def test_select_top_k_skips_invalid_higher_scoring_adapter(tmp_path: Path) -> None:
    team = tmp_path / "team"
    broken = _make_candidate(team, "broken", 50.0, 1.0)
    _make_candidate(team, "champion", 40.0, 2.0)
    _make_candidate(team, "runner", 30.0, 3.0)

    def validator(path: str) -> Path:
        if Path(path) == broken:
            raise ValueError("broken adapter")
        return Path(path)

    selected, candidates = select_top_candidates(
        team,
        top_k=2,
        expected_suite="joint",
        expected_inference_backend="vllm",
        validator=validator,
    )

    assert [candidate.run_id for candidate in selected] == ["champion", "runner"]
    rejected = next(candidate for candidate in candidates if candidate.run_id == "broken")
    assert "model validation failed: broken adapter" in rejected.reasons


def test_select_top_k_fails_when_not_enough_valid_candidates(tmp_path: Path) -> None:
    team = tmp_path / "team"
    _make_candidate(team, "only", 10.0, 1.0)

    with pytest.raises(CompetitionExportError, match="requested top 2"):
        select_top_candidates(team, top_k=2, validator=lambda path: Path(path))


def test_rendered_job_script_is_valid_bash_and_binds_checksum(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate with space"
    packager = tmp_path / "competition" / "package_adapter_spipe.py"
    script = render_job_script(
        candidate_dir=candidate,
        adapter_dir=tmp_path / "adapter with space",
        base_model="google/gemma-4-31B-it",
        base_sif=tmp_path / "base.sif",
        starter_kit=tmp_path / "kit",
        hf_cache=tmp_path / "hf cache",
        packager=packager,
        account="ram",
        partition="g3",
        qos="g3_ram_high",
        cpus=24,
        memory="200G",
        walltime="02:00:00",
    )
    path = tmp_path / "job.sbatch"
    path.write_text(script, encoding="utf-8")

    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0
    assert "/opt/source_model_checksums.json:ro" in script
    assert "--source-checksums /opt/source_model_checksums.json" in script
    assert model_slug("google/gemma-4-31B-it") == "google__gemma-4-31B-it"


def test_huggingface_default_paths_distinguish_top_k(tmp_path: Path) -> None:
    bundle = tmp_path / "google__gemma-4-31B-it.spipe"
    args = Namespace(hf_path_template=None, top_k=2)
    record = {"rank": 2, "run_id": "run/id", "idea_name": "idea"}

    assert _remote_path(args, record, bundle) == "02-run_id/google__gemma-4-31B-it.spipe"


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", True])
def test_parse_bool_true(value: str | bool) -> None:
    assert _parse_bool(value) is True


def test_method_hash_matches_expected_concatenation(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    expected = hashlib.sha256("# ===== a.py =====\na = 1\n".encode()).hexdigest()
    assert method_code_hash(tmp_path) == expected


def _install_fake_hub(monkeypatch: pytest.MonkeyPatch, api_type: type) -> None:
    hub = types.ModuleType("huggingface_hub")
    hub.HfApi = api_type
    errors = types.ModuleType("huggingface_hub.errors")
    errors.HfHubHTTPError = type("HfHubHTTPError", (Exception,), {})
    errors.RepositoryNotFoundError = type("RepositoryNotFoundError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", errors)


def _upload_fixture(tmp_path: Path) -> tuple[dict, Namespace, str]:
    candidate = tmp_path / "candidate"
    submission = candidate / "work" / "submission"
    submission.mkdir(parents=True)
    bundle = submission / "model.spipe"
    bundle.write_bytes(b"spipe bytes")
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    _write_json(submission / "bundle_report.json", {"ok": True, "sha256": digest})
    record = {
        "rank": 1,
        "run_id": "run-1",
        "idea_name": "idea",
        "candidate_dir": str(candidate),
        "bundle": str(bundle),
    }
    args = Namespace(
        hf_repo="owner/repo",
        hf_repo_type="model",
        hf_revision=None,
        hf_create_repo=False,
        hf_visibility=None,
        hf_overwrite=False,
        hf_path_template=None,
        top_k=1,
    )
    return record, args, digest


def test_upload_preflights_collision_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, args, _ = _upload_fixture(tmp_path)

    class FakeApi:
        uploads = 0

        def whoami(self):
            return {"name": "tester"}

        def repo_info(self, *args, **kwargs):
            return SimpleNamespace(default_branch="main", private=True)

        def list_repo_files(self, *args, **kwargs):
            return ["model.spipe"]

        def upload_file(self, **kwargs):
            type(self).uploads += 1

    _install_fake_hub(monkeypatch, FakeApi)

    with pytest.raises(CompetitionExportError, match="already exist"):
        upload_bundles(args, [record])
    assert FakeApi.uploads == 0


def test_upload_verifies_immutable_commit_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, args, digest = _upload_fixture(tmp_path)
    size = Path(record["bundle"]).stat().st_size

    class FakeApi:
        def whoami(self):
            return {"name": "tester"}

        def repo_info(self, *args, **kwargs):
            return SimpleNamespace(default_branch="main", private=True)

        def list_repo_files(self, *args, **kwargs):
            return []

        def upload_file(self, **kwargs):
            assert kwargs["path_in_repo"] == "model.spipe"
            return SimpleNamespace(oid="abc123", commit_url="https://huggingface.co/commit/abc123")

        def get_paths_info(self, *args, **kwargs):
            assert kwargs["revision"] == "abc123"
            return [SimpleNamespace(size=size, lfs=SimpleNamespace(sha256=digest))]

    _install_fake_hub(monkeypatch, FakeApi)
    reports = upload_bundles(args, [record])

    assert reports[0]["commit_oid"] == "abc123"
    assert reports[0]["byte_identity_verified"] is True
    assert reports[0]["repository_private"] is True
    assert (Path(record["candidate_dir"]) / "upload.json").is_file()
