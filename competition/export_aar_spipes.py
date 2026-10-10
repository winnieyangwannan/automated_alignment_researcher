#!/usr/bin/env python3
"""Select AAR champions, package them as fat `.spipe` bundles, and optionally upload them."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aar.transport import validate_model_submission  # noqa: E402


class CompetitionExportError(RuntimeError):
    """The requested champion export is unsafe, ambiguous, or incomplete."""


@dataclass
class Candidate:
    run_id: str
    score_path: Path
    score: dict[str, Any] = field(default_factory=dict)
    proposal_path: Path | None = None
    proposal: dict[str, Any] = field(default_factory=dict)
    finding_path: Path | None = None
    finding: dict[str, Any] = field(default_factory=dict)
    method_path: Path | None = None
    model_path: Path | None = None
    idea_name: str | None = None
    headline_pct: float | None = None
    proposal_ts: float = math.inf
    artifact_type: str | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def metadata_eligible(self) -> bool:
        return not self.reasons

    def rank_key(self) -> tuple[float, float, str]:
        assert self.headline_pct is not None
        return (-self.headline_pct, self.proposal_ts, self.run_id)

    def summary(self, *, selected_rank: int | None = None) -> dict[str, Any]:
        if selected_rank is not None:
            status = "selected"
        elif self.metadata_eligible:
            status = "eligible"
        else:
            status = "rejected"
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "idea_name": self.idea_name,
            "headline_pct": self.headline_pct,
            "artifact_type": self.artifact_type,
            "passes_filter": self.score.get("passes_filter"),
            "passes_regression": self.score.get("passes_regression"),
            "status": status,
            "reasons": self.reasons,
            "warnings": self.warnings,
        }
        if selected_rank is not None:
            result["rank"] = selected_rank
        return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_component(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and all(
        char.isalnum() or char in "-_" for char in value
    )


def _safe_run_filename(run_id: str) -> str:
    return "".join(
        char if (char.isalnum() or char in "_.:-") else "_"
        for char in (run_id or "run")
    )


def model_slug(model: str) -> str:
    """Match starterkit.model_slug without importing the competition environment."""
    return re.sub(r"[^A-Za-z0-9._-]", "__", model)


def method_code_hash(method_dir: Path) -> str | None:
    parts: list[str] = []
    for path in sorted(method_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts.append(
            f"# ===== {path.relative_to(method_dir)} =====\n"
            + path.read_text(encoding="utf-8", errors="ignore")
        )
    if not parts:
        return None
    return hashlib.sha256("\n\n".join(parts).encode()).hexdigest()


def _findings_by_run_id(forum_dir: Path) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    findings: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    if not forum_dir.is_dir():
        return findings
    for path in sorted(forum_dir.glob("*.json")):
        try:
            finding = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        run_id = finding.get("run_id")
        if isinstance(run_id, str) and finding.get("finding_type") == "result":
            findings.setdefault(run_id, []).append((path, finding))
    return findings


def _select_method_source(team_dir: Path, candidate: Candidate) -> Path | None:
    if not candidate.idea_name or not _safe_component(candidate.idea_name):
        return None
    expected_hash = candidate.proposal.get("code_hash")
    choices = [team_dir / "methods" / candidate.idea_name]
    snapshot = candidate.finding.get("code_snapshot")
    if isinstance(snapshot, str) and _safe_component(snapshot):
        choices.append(team_dir / "forum" / snapshot)
    for choice in choices:
        if choice.is_dir() and method_code_hash(choice) == expected_hash:
            return choice
    return None


def _protocol_signature(score: dict[str, Any]) -> str:
    entries = []
    per_benchmark = score.get("per_benchmark")
    if isinstance(per_benchmark, dict):
        for name, details in sorted(per_benchmark.items()):
            details = details if isinstance(details, dict) else {}
            entries.append(
                {
                    "name": name,
                    "role": details.get("role"),
                    "baseline": details.get("baseline"),
                    "optimum": details.get("optimum"),
                    "floor": details.get("floor"),
                }
            )
    return json.dumps(
        {
            "suite": score.get("suite"),
            "inference_backend": score.get("inference_backend"),
            "aggregation": score.get("aggregation"),
            "benchmarks": entries,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def discover_candidates(
    team_dir: Path,
    *,
    expected_suite: str | None = None,
    expected_inference_backend: str | None = None,
) -> list[Candidate]:
    team_dir = team_dir.resolve(strict=True)
    scores_dir = team_dir / "scores"
    submissions_dir = team_dir / "submissions"
    if not scores_dir.is_dir():
        raise CompetitionExportError(f"scores directory does not exist: {scores_dir}")
    findings = _findings_by_run_id(team_dir / "forum")
    candidates: list[Candidate] = []

    for score_path in sorted(scores_dir.glob("*.json")):
        if score_path.name.endswith(".failed.json"):
            continue
        candidate = Candidate(run_id=score_path.stem, score_path=score_path)
        candidates.append(candidate)
        try:
            candidate.score = _read_json(score_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            candidate.reasons.append(f"invalid score JSON: {error}")
            continue

        score = candidate.score
        headline = score.get("headline_pct")
        if isinstance(headline, bool) or not isinstance(headline, (int, float)):
            candidate.reasons.append("headline_pct is missing or non-numeric")
        elif not math.isfinite(float(headline)):
            candidate.reasons.append("headline_pct is not finite")
        else:
            candidate.headline_pct = float(headline)
        if score.get("error"):
            candidate.reasons.append("score contains an evaluator error")
        if not isinstance(score.get("per_benchmark"), dict) or not score["per_benchmark"]:
            candidate.reasons.append("score has no per_benchmark results")
        if score.get("passes_filter") is not True:
            candidate.reasons.append("capability/regression filter did not pass")
        if score.get("passes_regression") is False:
            candidate.reasons.append("safety regression gate did not pass")
        if expected_suite and score.get("suite") != expected_suite:
            candidate.reasons.append(
                f"suite is {score.get('suite')!r}, expected {expected_suite!r}"
            )
        if expected_inference_backend and score.get("inference_backend") != expected_inference_backend:
            candidate.reasons.append(
                "inference backend is "
                f"{score.get('inference_backend')!r}, expected {expected_inference_backend!r}"
            )

        proposal_path = (
            scores_dir / ".proposals" / "runs" / f"{_safe_run_filename(candidate.run_id)}.json"
        )
        candidate.proposal_path = proposal_path
        if not proposal_path.is_file():
            candidate.reasons.append("approved per-run proposal is missing")
        else:
            try:
                candidate.proposal = _read_json(proposal_path)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                candidate.reasons.append(f"invalid approved proposal: {error}")
            else:
                if candidate.proposal.get("run_id") != candidate.run_id:
                    candidate.reasons.append("proposal run_id does not match score")
                idea_name = candidate.proposal.get("idea_name")
                if not isinstance(idea_name, str) or not _safe_component(idea_name):
                    candidate.reasons.append("proposal has no safe idea_name")
                else:
                    candidate.idea_name = idea_name
                code_hash = candidate.proposal.get("code_hash")
                if not (
                    isinstance(code_hash, str)
                    and len(code_hash) == 64
                    and all(char in "0123456789abcdef" for char in code_hash)
                ):
                    candidate.reasons.append("proposal has no approved code hash")
                proposal_ts = candidate.proposal.get("proposal_ts")
                if isinstance(proposal_ts, (int, float)):
                    candidate.proposal_ts = float(proposal_ts)
                if not isinstance(candidate.proposal.get("paper"), dict):
                    candidate.reasons.append("proposal has no frozen mini-paper")

        matches = findings.get(candidate.run_id, [])
        if matches:
            candidate.finding_path, candidate.finding = matches[0]
            if len(matches) > 1:
                candidate.warnings.append(
                    f"found {len(matches)} result findings for this run_id"
                )
        else:
            candidate.warnings.append("no successfully shared result finding was found")

        candidate.model_path = submissions_dir / candidate.run_id / "model"
        if not candidate.model_path.is_dir():
            candidate.reasons.append("evaluated model artifact is missing")
        elif (candidate.model_path / "adapter_config.json").is_file():
            candidate.artifact_type = "adapter"
        elif (candidate.model_path / "config.json").is_file():
            candidate.artifact_type = "full_model"
        else:
            candidate.reasons.append("model artifact is neither an adapter nor full model")

        if candidate.idea_name:
            candidate.method_path = _select_method_source(team_dir, candidate)
            if candidate.method_path is None:
                candidate.reasons.append(
                    "no method source matches the approved proposal code hash"
                )

    if not candidates:
        raise CompetitionExportError(f"no completed score JSON files under {scores_dir}")
    return candidates


def select_top_candidates(
    team_dir: Path,
    *,
    top_k: int,
    expected_suite: str | None = None,
    expected_inference_backend: str | None = None,
    validator: Callable[[str], Path] = validate_model_submission,
) -> tuple[list[Candidate], list[Candidate]]:
    if top_k < 1:
        raise ValueError("top_k must be positive")
    candidates = discover_candidates(
        team_dir,
        expected_suite=expected_suite,
        expected_inference_backend=expected_inference_backend,
    )
    eligible = [candidate for candidate in candidates if candidate.metadata_eligible]
    if not eligible:
        details = "; ".join(
            f"{candidate.run_id}: {', '.join(candidate.reasons)}"
            for candidate in candidates
        )
        raise CompetitionExportError(f"no metadata-valid candidate: {details}")
    protocols = {_protocol_signature(candidate.score) for candidate in eligible}
    if len(protocols) != 1:
        raise CompetitionExportError(
            "eligible candidates use different suites, benchmark baselines, aggregation rules, "
            "or inference backends; filter or export those protocols separately"
        )

    selected: list[Candidate] = []
    for candidate in sorted(eligible, key=Candidate.rank_key):
        if candidate.artifact_type != "adapter":
            candidate.reasons.append(
                f"artifact type is {candidate.artifact_type!r}; `.spipe` export currently requires an adapter"
            )
            continue
        assert candidate.model_path is not None
        try:
            validator(str(candidate.model_path))
        except Exception as error:
            candidate.reasons.append(f"model validation failed: {error}")
            continue
        selected.append(candidate)
        if len(selected) == top_k:
            break
    if not selected:
        details = "; ".join(
            f"{candidate.run_id}: {', '.join(candidate.reasons)}"
            for candidate in eligible
        )
        raise CompetitionExportError(f"no exportable adapter candidate: {details}")
    if len(selected) < top_k:
        raise CompetitionExportError(
            f"requested top {top_k}, but only {len(selected)} valid adapter candidate(s) exist"
        )
    return selected, candidates


def resolve_team_dir(team_dir: Path | None, attempt_dir: Path | None) -> Path:
    if team_dir is not None:
        return team_dir.expanduser().resolve(strict=True)
    assert attempt_dir is not None
    teams_root = attempt_dir.expanduser().resolve(strict=True) / "aar_teams"
    teams = sorted(path for path in teams_root.iterdir() if path.is_dir())
    if len(teams) != 1:
        raise CompetitionExportError(
            f"expected exactly one team under {teams_root}, found {len(teams)}; pass --team-dir"
        )
    return teams[0]


def infer_base_model(candidate: Candidate, override: str | None) -> str:
    if override:
        model = override
    else:
        assert candidate.model_path is not None
        config = _read_json(candidate.model_path / "adapter_config.json")
        model = config.get("base_model_name_or_path")
    if not isinstance(model, str) or not model:
        raise CompetitionExportError("adapter does not identify a base model; pass --base-model")
    if Path(model).is_absolute():
        raise CompetitionExportError(
            f"base model is a local path ({model}); pass a portable Hub identifier with --base-model"
        )
    return model


def _tree_checksums(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CompetitionExportError(f"adapter contains a symbolic link: {path}")
        if path.is_file():
            result[str(path.relative_to(root))] = {
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
    if not result:
        raise CompetitionExportError(f"adapter directory is empty: {root}")
    return result


_METHOD_SKIP_DIRS = {".git", "__pycache__", "checkpoints", "model", "models", "outputs", "wandb"}
_METHOD_SKIP_EXTENSIONS = {".bin", ".ckpt", ".gguf", ".h5", ".onnx", ".pt", ".pth", ".pyc", ".safetensors"}


def _copy_method_source(source: Path, destination: Path) -> list[str]:
    omitted: list[str] = []
    destination.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in _METHOD_SKIP_DIRS for part in relative.parts):
            if path.is_file():
                omitted.append(str(relative))
            continue
        if path.is_symlink() or path.suffix in _METHOD_SKIP_EXTENSIONS:
            omitted.append(str(relative))
            continue
        if path.is_dir():
            (destination / relative).mkdir(parents=True, exist_ok=True)
            continue
        if path.stat().st_size > 5 * 1024 * 1024:
            omitted.append(str(relative))
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return omitted


def _method_card(candidate: Candidate, base_model: str) -> str:
    paper = candidate.proposal.get("paper")
    paper = paper if isinstance(paper, dict) else {}
    title = paper.get("title") or candidate.idea_name or "AAR champion"
    summary_parts = [paper.get("abstract"), paper.get("method")]
    summary = "\n\n".join(str(value).strip() for value in summary_parts if value) or "Not recorded."
    data = str(paper.get("data") or "Not recorded.").strip()
    result = str(candidate.finding.get("results_writeup") or "Not recorded.").strip()
    return (
        f"# {title}\n\n"
        f"## Summary\n\n{summary}\n\n"
        "## Controls\n\n"
        f"- `structural_control/load_lora` — the evaluated adapter for `{base_model}`.\n\n"
        f"## Data\n\n{data}\n\n"
        "## AAR provenance\n\n"
        f"- Run ID: `{candidate.run_id}`\n"
        f"- Idea: `{candidate.idea_name}`\n"
        f"- Headline: `{candidate.headline_pct:.2f}%`\n"
        f"- Suite: `{candidate.score.get('suite')}`\n\n"
        f"## Results\n\n{result}\n"
    )


def _pipeline_source() -> str:
    return '''"""Competition seam generated from an exact evaluated AAR adapter."""

from starterkit import model_slug
from steer_core import ARTIFACTS_DIR
from steerability.algorithms.structural_control.load_lora import LoadLoRA


def build_controls(model: str) -> list:
    return [
        LoadLoRA(
            path=f"{ARTIFACTS_DIR}/{model_slug(model)}-lora",
            base_model=model,
        )
    ]
'''


def _git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _shell_assignment(name: str, value: str | Path) -> str:
    return f"{name}={shlex.quote(str(value))}"


def render_job_script(
    *,
    candidate_dir: Path,
    adapter_dir: Path,
    base_model: str,
    base_sif: Path,
    starter_kit: Path,
    hf_cache: Path,
    packager: Path,
    account: str,
    partition: str,
    qos: str,
    cpus: int,
    memory: str,
    walltime: str,
) -> str:
    slug = model_slug(base_model)
    work = candidate_dir / "work"
    tmp = candidate_dir / "tmp"
    logs = candidate_dir / "logs"
    checksums = candidate_dir / "provenance" / "source_model_checksums.json"
    venv = starter_kit / ".venv"
    job_name = f"aar-spipe-{candidate_dir.name}"[:120]
    lines = [
        "#!/usr/bin/env bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --account={account}",
        f"#SBATCH --partition={partition}",
        f"#SBATCH --qos={qos}",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --gpus-per-node=1",
        f"#SBATCH --cpus-per-task={cpus}",
        f"#SBATCH --mem={memory}",
        f"#SBATCH --time={walltime}",
        f"#SBATCH --output={logs}/package-%j.log",
        "set -euo pipefail",
        f"mkdir -p {shlex.quote(str(work / 'submission'))} {shlex.quote(str(tmp))} {shlex.quote(str(logs))}",
        "apptainer exec --nvccli --containall --cleanenv --no-home --writable-tmpfs \\",
        f"  --bind {shlex.quote(str(packager.parent))}:/opt/aar-competition:ro \\",
        f"  --bind {shlex.quote(str(starter_kit))}:/opt/starter-kit:ro \\",
        f"  --bind {shlex.quote(str(venv))}:/opt/steer-venv:ro \\",
        f"  --bind {shlex.quote(str(work))}:/workspace \\",
        f"  --bind {shlex.quote(str(adapter_dir))}:/adapter:ro \\",
        f"  --bind {shlex.quote(str(tmp))}:/tmp \\",
        f"  --bind {shlex.quote(str(hf_cache))}:/root/.cache/huggingface:ro \\",
        f"  --bind {shlex.quote(str(checksums))}:/opt/source_model_checksums.json:ro \\",
        "  --bind /checkpoint --bind /storage \\",
        "  --env HF_HOME=/root/.cache/huggingface \\",
        "  --env HF_HUB_OFFLINE=1 --env TRANSFORMERS_OFFLINE=1 \\",
        "  --env PYTHONPATH=/opt/starter-kit \\",
        f"  {shlex.quote(str(base_sif))} /opt/steer-venv/bin/python /opt/aar-competition/package_adapter_spipe.py \\",
        "  --adapter-dir /adapter \\",
        f"  --base-model {shlex.quote(base_model)} \\",
        "  --output-dir /workspace/submission \\",
        "  --source-checksums /opt/source_model_checksums.json \\",
        f"  --expected-filename {shlex.quote(slug + '.spipe')}",
    ]
    return "\n".join(lines) + "\n"


def _safe_output(output_dir: Path, team_dir: Path, *, force: bool) -> Path:
    output = output_dir.expanduser().absolute()
    if output in {Path("/"), Path.home()}:
        raise CompetitionExportError(f"unsafe output directory: {output}")
    team = team_dir.resolve()
    if output == team or team in output.parents or output in team.parents:
        raise CompetitionExportError(
            "output directory must be outside the team directory and must not contain it"
        )
    if output.is_symlink():
        raise CompetitionExportError("output directory cannot be a symbolic link")
    if output.exists():
        if not force:
            raise CompetitionExportError(
                f"output directory already exists (pass --force to replace it): {output}"
            )
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def prepare_export(args: argparse.Namespace) -> tuple[Path, list[dict[str, Any]]]:
    team_dir = resolve_team_dir(args.team_dir, args.attempt_dir)
    output_dir = _safe_output(args.output_dir, team_dir, force=args.force)
    selected, candidates = select_top_candidates(
        team_dir,
        top_k=args.top_k,
        expected_suite=args.suite,
        expected_inference_backend=args.inference_backend,
    )
    base_models = [infer_base_model(candidate, args.base_model) for candidate in selected]
    if len(set(base_models)) != 1:
        raise CompetitionExportError(
            f"selected candidates identify different base models: {sorted(set(base_models))}"
        )

    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.incomplete-", dir=output_dir.parent))
    records: list[dict[str, Any]] = []
    try:
        for rank, (candidate, base_model) in enumerate(zip(selected, base_models, strict=True), 1):
            assert candidate.model_path is not None
            assert candidate.method_path is not None
            candidate_name = f"rank-{rank:02d}_{_safe_run_filename(candidate.run_id)}"
            candidate_stage = staging / candidate_name
            candidate_final = output_dir / candidate_name
            provenance = candidate_stage / "provenance"
            work = candidate_stage / "work"
            submission = work / "submission"
            provenance.mkdir(parents=True)
            submission.mkdir(parents=True)
            (candidate_stage / "logs").mkdir()
            (candidate_stage / "tmp").mkdir()

            shutil.copy2(candidate.score_path, provenance / "score.json")
            assert candidate.proposal_path is not None
            shutil.copy2(candidate.proposal_path, provenance / "proposal.json")
            if candidate.finding_path:
                shutil.copy2(candidate.finding_path, provenance / "finding.json")
            omitted = _copy_method_source(candidate.method_path, provenance / "method")
            _write_json(
                provenance / "source_model_checksums.json",
                _tree_checksums(candidate.model_path),
            )
            (work / "pipeline.py").write_text(_pipeline_source(), encoding="utf-8")
            (submission / "method_card.md").write_text(
                _method_card(candidate, base_model), encoding="utf-8"
            )
            record = {
                "rank": rank,
                "run_id": candidate.run_id,
                "idea_name": candidate.idea_name,
                "headline_pct": candidate.headline_pct,
                "base_model": base_model,
                "model_slug": model_slug(base_model),
                "source_model": str(candidate.model_path.resolve()),
                "source_score": str(candidate.score_path.resolve()),
                "candidate_dir": str(candidate_final),
                "bundle": str(candidate_final / "work" / "submission" / f"{model_slug(base_model)}.spipe"),
                "omitted_method_files": omitted,
            }
            _write_json(provenance / "candidate.json", record)
            records.append(record)

        selected_ranks = {candidate.run_id: rank for rank, candidate in enumerate(selected, 1)}
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": _git_commit(),
            "team_dir": str(team_dir),
            "selection": {
                "metric": "headline_pct",
                "direction": "maximize",
                "top_k": args.top_k,
                "tie_break": "earliest proposal timestamp, then lexical run_id",
                "suite": args.suite,
                "inference_backend": args.inference_backend,
            },
            "selected": records,
            "candidates": [
                candidate.summary(selected_rank=selected_ranks.get(candidate.run_id))
                for candidate in sorted(candidates, key=lambda item: item.run_id)
            ],
        }
        _write_json(staging / "selection.json", manifest)
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return output_dir, records


def _validate_runtime_paths(args: argparse.Namespace) -> None:
    required = {
        "base SIF": args.base_sif,
        "starter kit": args.starter_kit,
        "starter-kit venv": args.starter_kit / ".venv",
        "Hugging Face cache": args.hf_cache,
        "packager": Path(__file__).with_name("package_adapter_spipe.py"),
    }
    missing = [f"{name}: {path}" for name, path in required.items() if not path.exists()]
    if missing:
        raise CompetitionExportError("missing export runtime path(s): " + "; ".join(missing))


def write_job_scripts(args: argparse.Namespace, output_dir: Path, records: list[dict[str, Any]]) -> list[Path]:
    packager = Path(__file__).with_name("package_adapter_spipe.py").resolve()
    scripts: list[Path] = []
    for record in records:
        candidate_dir = Path(record["candidate_dir"])
        script = candidate_dir / "package.sbatch"
        script.write_text(
            render_job_script(
                candidate_dir=candidate_dir,
                adapter_dir=Path(record["source_model"]),
                base_model=record["base_model"],
                base_sif=args.base_sif,
                starter_kit=args.starter_kit,
                hf_cache=args.hf_cache,
                packager=packager,
                account=args.account,
                partition=args.partition,
                qos=args.qos,
                cpus=args.cpus,
                memory=args.memory,
                walltime=args.time,
            ),
            encoding="utf-8",
        )
        script.chmod(0o755)
        scripts.append(script)
    return scripts


def submit_jobs(scripts: Iterable[Path]) -> dict[str, str]:
    jobs: dict[str, str] = {}
    for script in scripts:
        completed = subprocess.run(
            ["sbatch", "--parsable", str(script)],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise CompetitionExportError(
                f"sbatch failed for {script}: {completed.stderr.strip()}"
            )
        job_id = completed.stdout.strip().split(";", 1)[0]
        if not job_id.isdigit():
            raise CompetitionExportError(f"could not parse sbatch job id: {completed.stdout!r}")
        jobs[script.parent.name] = job_id
    return jobs


_TERMINAL_STATES = {
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED", "NODE_FAIL",
    "OUT_OF_MEMORY", "PREEMPTED", "REVOKED", "TIMEOUT",
}


def wait_for_jobs(jobs: dict[str, str], poll_seconds: int) -> dict[str, str]:
    pending = dict(jobs)
    states: dict[str, str] = {}
    while pending:
        for name, job_id in list(pending.items()):
            completed = subprocess.run(
                ["sacct", "-n", "-X", "-j", job_id, "--format=State", "--parsable2"],
                capture_output=True,
                text=True,
            )
            values = [line.strip().split("|", 1)[0] for line in completed.stdout.splitlines() if line.strip()]
            state = values[0].split("+", 1)[0] if values else ""
            if state in _TERMINAL_STATES:
                states[name] = state
                del pending[name]
        if pending:
            time.sleep(poll_seconds)
    return states


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected a boolean, got {value!r}")


def _remote_path(args: argparse.Namespace, record: dict[str, Any], bundle: Path) -> str:
    template = args.hf_path_template
    if template is None:
        template = "{filename}" if args.top_k == 1 else "{rank:02d}-{run_id}/{filename}"
    path = template.format(
        rank=record["rank"],
        run_id=_safe_run_filename(record["run_id"]),
        idea_name=record["idea_name"] or "unknown",
        filename=bundle.name,
    ).lstrip("/")
    if not path or any(part in {"", ".", ".."} for part in Path(path).parts):
        raise CompetitionExportError(f"unsafe rendered Hugging Face path: {path!r}")
    return path


def upload_bundles(args: argparse.Namespace, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError
    except ImportError as error:
        raise CompetitionExportError(
            "--upload requires huggingface_hub in the launcher environment"
        ) from error

    api = HfApi()
    try:
        identity = api.whoami()
    except Exception as error:
        raise CompetitionExportError(
            "Hugging Face authentication failed; authenticate with a write-scoped token"
        ) from error

    created_repo = False
    try:
        repo_info = api.repo_info(args.hf_repo, repo_type=args.hf_repo_type)
    except (RepositoryNotFoundError, HfHubHTTPError) as error:
        status = getattr(getattr(error, "response", None), "status_code", None)
        if status not in {401, 403, 404, None} or not args.hf_create_repo:
            raise CompetitionExportError(
                f"Hugging Face repository is unavailable: {args.hf_repo}"
            ) from error
        if args.hf_visibility is None:
            raise CompetitionExportError(
                "creating a repository requires --hf-private or --hf-public"
            )
        api.create_repo(
            args.hf_repo,
            repo_type=args.hf_repo_type,
            private=args.hf_visibility == "private",
            exist_ok=False,
        )
        created_repo = True
        repo_info = api.repo_info(args.hf_repo, repo_type=args.hf_repo_type)

    revision = args.hf_revision or getattr(repo_info, "default_branch", None) or "main"
    if created_repo:
        existing: set[str] = set()
    else:
        try:
            existing = set(
                api.list_repo_files(
                    args.hf_repo,
                    repo_type=args.hf_repo_type,
                    revision=revision,
                )
            )
        except Exception as error:
            raise CompetitionExportError(
                f"could not preflight Hugging Face revision {revision!r}"
            ) from error

    plans: list[dict[str, Any]] = []
    for record in records:
        bundle = Path(record["bundle"])
        bundle_report_path = bundle.parent / "bundle_report.json"
        if not bundle.is_file() or not bundle_report_path.is_file():
            raise CompetitionExportError(f"verified bundle is missing: {bundle}")
        bundle_report = _read_json(bundle_report_path)
        if bundle_report.get("ok") is not True:
            raise CompetitionExportError(f"bundle verification did not pass: {bundle}")
        digest = _sha256(bundle)
        if digest != bundle_report.get("sha256"):
            raise CompetitionExportError(f"bundle changed after verification: {bundle}")
        remote_path = _remote_path(args, record, bundle)
        size = bundle.stat().st_size
        plans.append(
            {
                "record": record,
                "bundle": bundle,
                "digest": digest,
                "remote_path": remote_path,
                "size": size,
            }
        )

    remote_paths = [plan["remote_path"] for plan in plans]
    if len(set(remote_paths)) != len(remote_paths):
        raise CompetitionExportError(
            f"Hugging Face path template produced duplicate paths: {remote_paths}"
        )
    collisions = sorted(set(remote_paths) & existing)
    if collisions and not args.hf_overwrite:
        raise CompetitionExportError(
            "remote file(s) already exist; pass --hf-overwrite to replace them: "
            + ", ".join(collisions)
        )

    reports: list[dict[str, Any]] = []
    for plan in plans:
        record = plan["record"]
        bundle = plan["bundle"]
        digest = plan["digest"]
        remote_path = plan["remote_path"]
        size = plan["size"]
        commit = api.upload_file(
            path_or_fileobj=str(bundle),
            path_in_repo=remote_path,
            repo_id=args.hf_repo,
            repo_type=args.hf_repo_type,
            revision=revision,
            commit_message=f"Upload SPipe {digest[:12]}",
            commit_description=(
                f"Local SHA-256: {digest}\n"
                f"Size: {size} bytes\n"
                f"AAR run ID: {record['run_id']}\n"
                f"AAR source commit: {_git_commit() or 'unknown'}"
            ),
        )
        oid = getattr(commit, "oid", None)
        if not oid:
            raise CompetitionExportError(f"Hub upload returned no commit OID for {remote_path}")
        paths = api.get_paths_info(
            args.hf_repo,
            paths=[remote_path],
            repo_type=args.hf_repo_type,
            revision=oid,
        )
        if len(paths) != 1:
            raise CompetitionExportError(
                f"uploaded path was not found at immutable commit {oid}: {remote_path}"
            )
        remote = paths[0]
        remote_size = getattr(remote, "size", None)
        if remote_size is not None and remote_size != size:
            raise CompetitionExportError(
                f"remote size mismatch for {remote_path}: {remote_size} != {size}"
            )
        lfs = getattr(remote, "lfs", None)
        remote_sha = None
        if lfs is not None:
            remote_sha = getattr(lfs, "sha256", None) or getattr(lfs, "oid", None)
            if isinstance(lfs, dict):
                remote_sha = lfs.get("sha256") or lfs.get("oid")
        identity_verified = remote_sha == digest if remote_sha else False
        repo_prefix = {"model": "", "dataset": "datasets/", "space": "spaces/"}[
            args.hf_repo_type
        ]
        report = {
            "repo_id": args.hf_repo,
            "repo_type": args.hf_repo_type,
            "revision": revision,
            "commit_oid": oid,
            "commit_url": str(getattr(commit, "commit_url", "")),
            "file_url": (
                f"https://huggingface.co/{repo_prefix}{args.hf_repo}/blob/"
                f"{oid}/{quote(remote_path)}"
            ),
            "path_in_repo": remote_path,
            "local_path": str(bundle.resolve()),
            "local_sha256": digest,
            "local_size_bytes": size,
            "remote_size_bytes": remote_size,
            "remote_object_sha256": remote_sha,
            "byte_identity_verified": identity_verified,
            "repository_private": getattr(repo_info, "private", None),
            "authenticated_name": identity.get("name") if isinstance(identity, dict) else None,
        }
        _write_json(Path(record["candidate_dir"]) / "upload.json", report)
        reports.append(report)
        existing.add(remote_path)
    return reports


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--team-dir", type=Path)
    source.add_argument("--attempt-dir", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--suite")
    parser.add_argument("--inference-backend")
    parser.add_argument("--base-model")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="prepare and print jobs without submitting")
    parser.add_argument("--wait", action="store_true", help="wait for packaging jobs and validate completion")
    parser.add_argument("--poll-seconds", type=int, default=20)

    parser.add_argument("--base-sif", required=True, type=Path)
    parser.add_argument("--starter-kit", required=True, type=Path)
    parser.add_argument("--hf-cache", required=True, type=Path)
    parser.add_argument("--account", default=os.getenv("AAR_SPIPE_ACCOUNT", "ram"))
    parser.add_argument("--partition", default=os.getenv("AAR_SPIPE_PARTITION", "g3"))
    parser.add_argument("--qos", default=os.getenv("AAR_SPIPE_QOS", "g3_ram_high"))
    parser.add_argument("--cpus", type=int, default=24)
    parser.add_argument("--memory", default="200G")
    parser.add_argument("--time", default="02:00:00")

    parser.add_argument("--upload", nargs="?", const=True, default=False, type=_parse_bool)
    parser.add_argument("--hf-repo")
    parser.add_argument("--hf-repo-type", choices=("model", "dataset", "space"), default="model")
    parser.add_argument("--hf-revision")
    parser.add_argument("--hf-path-template")
    parser.add_argument("--hf-overwrite", action="store_true")
    parser.add_argument("--hf-create-repo", action="store_true")
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument("--hf-private", dest="hf_visibility", action="store_const", const="private")
    visibility.add_argument("--hf-public", dest="hf_visibility", action="store_const", const="public")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.upload and not args.hf_repo:
        raise CompetitionExportError("--upload requires --hf-repo")
    if args.upload and args.dry_run:
        raise CompetitionExportError("--upload cannot be combined with --dry-run")
    if args.poll_seconds < 1:
        raise CompetitionExportError("--poll-seconds must be positive")

    if not args.dry_run:
        _validate_runtime_paths(args)
    output_dir, records = prepare_export(args)
    scripts = write_job_scripts(args, output_dir, records)
    _write_json(output_dir / "jobs.json", {"submitted": False, "jobs": {}})
    if args.dry_run:
        print(json.dumps({"output_dir": str(output_dir), "job_scripts": [str(p) for p in scripts]}, indent=2))
        return 0

    jobs = submit_jobs(scripts)
    _write_json(
        output_dir / "jobs.json",
        {"submitted": True, "submitted_at": datetime.now(timezone.utc).isoformat(), "jobs": jobs},
    )
    print(json.dumps({"output_dir": str(output_dir), "jobs": jobs}, indent=2))
    if not (args.wait or args.upload):
        return 0

    states = wait_for_jobs(jobs, args.poll_seconds)
    _write_json(output_dir / "job_states.json", states)
    failures = {name: state for name, state in states.items() if state != "COMPLETED"}
    if failures:
        raise CompetitionExportError(f"packaging job(s) failed: {failures}")
    for record in records:
        report_path = Path(record["bundle"]).parent / "bundle_report.json"
        if not report_path.is_file() or _read_json(report_path).get("ok") is not True:
            raise CompetitionExportError(f"bundle report did not pass: {report_path}")

    uploads = upload_bundles(args, records) if args.upload else []
    final = {"ok": True, "output_dir": str(output_dir), "jobs": jobs, "states": states, "uploads": uploads}
    _write_json(output_dir / "run_report.json", final)
    print(json.dumps(final, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CompetitionExportError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
