"""Select and package the highest-scoring valid model from one AAR team run.

The score handoff, approved proposal, and submitted model are all keyed by the
same ``run_id``.  This module joins those records directly instead of trusting
the forum leaderboard, which may contain seeded findings from older runs.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aar.transport import validate_model_submission


class ChampionExportError(RuntimeError):
    """The run does not contain one unambiguous, exportable champion."""


@dataclass
class Candidate:
    run_id: str
    score_path: Path
    score: dict[str, Any] = field(default_factory=dict)
    proposal_path: Path | None = None
    proposal: dict[str, Any] = field(default_factory=dict)
    finding_path: Path | None = None
    finding: dict[str, Any] = field(default_factory=dict)
    model_path: Path | None = None
    method_path: Path | None = None
    idea_name: str | None = None
    headline_pct: float | None = None
    proposal_ts: float = math.inf
    artifact_type: str | None = None
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fully_validated: bool = False

    @property
    def metadata_eligible(self) -> bool:
        return not self.reasons

    def rank_key(self) -> tuple[float, float, str]:
        """Sort key: higher headline, then earlier proposal and lexical run id."""
        assert self.headline_pct is not None
        return (-self.headline_pct, self.proposal_ts, self.run_id)

    def summary(self, selected: bool = False) -> dict[str, Any]:
        if selected:
            status = "selected"
        elif self.fully_validated:
            status = "valid"
        elif self.metadata_eligible:
            status = "metadata_eligible"
        else:
            status = "rejected"
        result: dict[str, Any] = {
            "run_id": self.run_id,
            "idea_name": self.idea_name,
            "headline_pct": self.headline_pct,
            "passes_filter": self.score.get("passes_filter"),
            "passes_regression": self.score.get("passes_regression"),
            "status": status,
            "reasons": self.reasons,
        }
        if self.artifact_type:
            result["artifact_type"] = self.artifact_type
        if self.warnings:
            result["warnings"] = self.warnings
        return result


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def _safe_run_filename(run_id: str) -> str:
    return "".join(
        char if (char.isalnum() or char in "_.:-") else "_"
        for char in (run_id or "run")
    )


def _safe_component(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and all(
        char.isalnum() or char in "-_" for char in value
    )


_FAILURE_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _terminal_failure_summary(scores_dir: Path, *, limit: int = 20) -> str | None:
    """Summarize failed runs without copying evaluator diagnostics.

    Failure markers may be research-readable, but their free-form reason and
    error fields can still contain prompts, held-out rows, paths, or secrets.
    Only schema-constrained identifiers are safe to echo in export errors.
    """

    summaries: list[str] = []
    failure_paths = sorted(scores_dir.glob("*.failed.json"))
    for failure_path in failure_paths[:limit]:
        run_id = failure_path.name[: -len(".failed.json")]
        safe_run_id = _safe_run_filename(run_id)
        stage = "unknown_stage"
        error_code = "invalid_failure_marker"
        try:
            failure = _read_json(failure_path)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        else:
            raw_stage = failure.get("stage")
            raw_error_code = failure.get("error_code")
            if isinstance(raw_stage, str) and _FAILURE_FIELD_RE.fullmatch(raw_stage):
                stage = raw_stage
            if (
                isinstance(raw_error_code, str)
                and _FAILURE_FIELD_RE.fullmatch(raw_error_code)
            ):
                error_code = raw_error_code
        summaries.append(f"{safe_run_id}:{stage}/{error_code}")
    if not summaries:
        return None
    omitted = len(failure_paths) - len(summaries)
    if omitted:
        summaries.append(f"and_{omitted}_more")
    return ", ".join(summaries)


def method_code_hash(method_dir: Path) -> str | None:
    """Reproduce the integrity monitor's hash over a method's Python files."""
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
    code = "\n\n".join(parts)
    return hashlib.sha256(code.encode()).hexdigest()


def _findings_by_run_id(forum_dir: Path) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    found: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    if not forum_dir.is_dir():
        return found
    for path in sorted(forum_dir.glob("*.json")):
        try:
            finding = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        run_id = finding.get("run_id")
        if isinstance(run_id, str) and finding.get("finding_type") == "result":
            found.setdefault(run_id, []).append((path, finding))
    return found


def _artifact_type(model_path: Path) -> str | None:
    if (model_path / "adapter_config.json").is_file():
        return "adapter"
    if (model_path / "config.json").is_file():
        return "full_model"
    return None


def _protocol_signature(score: dict[str, Any]) -> str:
    per_benchmark = score.get("per_benchmark")
    entries = []
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
    payload = {
        "suite": score.get("suite"),
        "inference_backend": score.get("inference_backend"),
        "aggregation": score.get("aggregation"),
        "benchmarks": entries,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _select_method_source(
    team_dir: Path,
    candidate: Candidate,
) -> Path | None:
    if not candidate.idea_name or not _safe_component(candidate.idea_name):
        return None
    expected_hash = candidate.proposal.get("code_hash")
    choices = [team_dir / "methods" / candidate.idea_name]
    snapshot = candidate.finding.get("code_snapshot")
    if isinstance(snapshot, str) and _safe_component(snapshot):
        choices.append(team_dir / "forum" / snapshot)
    for choice in choices:
        if not choice.is_dir():
            continue
        if expected_hash and method_code_hash(choice) != expected_hash:
            continue
        return choice
    return None


def discover_candidates(
    team_dir: Path,
    *,
    expected_suite: str | None = None,
    expected_inference_backend: str | None = None,
) -> list[Candidate]:
    """Read and metadata-check every terminal score in one team directory."""
    team_dir = team_dir.resolve(strict=True)
    scores_dir = team_dir / "scores"
    submissions_dir = team_dir / "submissions"
    if not scores_dir.is_dir():
        raise ChampionExportError(f"scores directory does not exist: {scores_dir}")
    findings = _findings_by_run_id(team_dir / "forum")
    candidates: list[Candidate] = []

    for score_path in sorted(scores_dir.glob("*.json")):
        if score_path.name.endswith(".failed.json"):
            continue
        run_id = score_path.stem
        candidate = Candidate(run_id=run_id, score_path=score_path)
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
        if (
            expected_inference_backend
            and score.get("inference_backend") != expected_inference_backend
        ):
            candidate.reasons.append(
                "inference backend is "
                f"{score.get('inference_backend')!r}, expected "
                f"{expected_inference_backend!r}"
            )

        proposal_path = (
            scores_dir
            / ".proposals"
            / "runs"
            / f"{_safe_run_filename(run_id)}.json"
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
                if candidate.proposal.get("run_id") != run_id:
                    candidate.reasons.append("proposal run_id does not match score")
                idea_name = candidate.proposal.get("idea_name")
                if not isinstance(idea_name, str) or not _safe_component(idea_name):
                    candidate.reasons.append("proposal has no safe idea_name")
                else:
                    candidate.idea_name = idea_name
                if not isinstance(candidate.proposal.get("paper"), dict):
                    candidate.reasons.append("proposal has no frozen mini-paper")
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

        matching_findings = findings.get(run_id, [])
        if matching_findings:
            candidate.finding_path, candidate.finding = matching_findings[0]
            if len(matching_findings) > 1:
                candidate.warnings.append(
                    f"found {len(matching_findings)} result findings for this run_id"
                )
        else:
            candidate.warnings.append("no successfully shared result finding was found")

        candidate.model_path = submissions_dir / run_id / "model"
        if not candidate.model_path.is_dir():
            candidate.reasons.append("evaluated model artifact is missing")
        else:
            candidate.artifact_type = _artifact_type(candidate.model_path)
            if not candidate.artifact_type:
                candidate.reasons.append("model artifact is neither an adapter nor full model")

        if candidate.idea_name:
            candidate.method_path = _select_method_source(team_dir, candidate)
            if not candidate.method_path:
                candidate.reasons.append(
                    "no method source matches the approved proposal code hash"
                )

    if not candidates:
        failure_summary = _terminal_failure_summary(scores_dir)
        detail = (
            f"; terminal failures: {failure_summary}" if failure_summary else ""
        )
        raise ChampionExportError(
            f"no completed score JSON files under {scores_dir}{detail}"
        )
    return candidates


def select_champion(
    team_dir: Path,
    *,
    expected_suite: str | None = None,
    expected_inference_backend: str | None = None,
    required_artifact_type: str = "either",
) -> tuple[Candidate, list[Candidate]]:
    """Return the best fully valid candidate and the complete audit list."""
    if required_artifact_type not in {"either", "adapter", "full_model"}:
        raise ValueError(
            "required_artifact_type must be either, adapter, or full_model"
        )
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
        raise ChampionExportError(f"no metadata-valid candidate: {details}")

    protocols = {_protocol_signature(candidate.score) for candidate in eligible}
    if len(protocols) != 1:
        raise ChampionExportError(
            "eligible candidates use different suites, benchmark baselines, "
            "aggregation rules, or inference backends; pass explicit filters or "
            "export the runs separately"
        )

    eligible.sort(key=Candidate.rank_key)
    for candidate in eligible:
        if required_artifact_type != "either" and (
            candidate.artifact_type != required_artifact_type
        ):
            candidate.reasons.append(
                f"artifact type is {candidate.artifact_type!r}, required "
                f"{required_artifact_type!r}"
            )
            continue
        assert candidate.model_path is not None
        try:
            validate_model_submission(str(candidate.model_path))
        except Exception as error:
            candidate.reasons.append(f"model validation failed: {error}")
            continue
        candidate.fully_validated = True
        return candidate, candidates

    details = "; ".join(
        f"{candidate.run_id}: {', '.join(candidate.reasons)}"
        for candidate in eligible
    )
    raise ChampionExportError(f"no exportable candidate artifact: {details}")


_METHOD_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".ipynb_checkpoints",
    "checkpoints",
    "model",
    "models",
    "outputs",
    "wandb",
}
_METHOD_SKIP_EXTENSIONS = {
    ".bin",
    ".ckpt",
    ".gguf",
    ".h5",
    ".onnx",
    ".pt",
    ".pth",
    ".pyc",
    ".safetensors",
}
_METHOD_MAX_FILE_BYTES = 5 * 1024 * 1024


def _copy_method_source(source: Path, destination: Path) -> list[str]:
    omitted: list[str] = []
    destination.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if any(part in _METHOD_SKIP_DIRS for part in relative.parts):
            if path.is_file():
                omitted.append(str(relative))
            continue
        if path.is_symlink():
            omitted.append(str(relative))
            continue
        if path.is_dir():
            (destination / relative).mkdir(parents=True, exist_ok=True)
            continue
        if path.suffix in _METHOD_SKIP_EXTENSIONS:
            omitted.append(str(relative))
            continue
        if path.stat().st_size > _METHOD_MAX_FILE_BYTES:
            omitted.append(str(relative))
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return omitted


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_checksums(root: Path) -> dict[str, dict[str, Any]]:
    checksums: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "checksums.json":
            checksums[str(path.relative_to(root))] = {
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
    return checksums


def _base_model(candidate: Candidate, override: str | None) -> str | None:
    if override:
        return override
    assert candidate.model_path is not None
    for name in ("adapter_config.json", "config.json"):
        path = candidate.model_path / name
        if not path.is_file():
            continue
        try:
            config = _read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        value = config.get("base_model_name_or_path") or config.get("_name_or_path")
        if isinstance(value, str) and value:
            return value
    return None


def _attempt_metadata(team_dir: Path) -> dict[str, str]:
    if team_dir.parent.name != "aar_teams":
        return {}
    metadata_path = team_dir.parent.parent / "metadata" / "submission.txt"
    if not metadata_path.is_file():
        return {}
    allowed = {
        "deployment",
        "git_commit",
        "mode",
        "research_backend",
        "research_model",
    }
    result: dict[str, str] = {}
    for line in metadata_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in allowed:
            result[key] = value
    return result


def _method_card(candidate: Candidate) -> str:
    paper = candidate.proposal.get("paper")
    paper = paper if isinstance(paper, dict) else {}
    title = paper.get("title") or candidate.idea_name or "AAR champion"
    sections = [
        ("Abstract", paper.get("abstract")),
        ("Motivation", paper.get("motivation")),
        ("Related Work", paper.get("related_work")),
        ("Method", paper.get("method")),
        ("Data", paper.get("data")),
        ("Experimental Setup", paper.get("experimental_setup")),
        ("Results and Discussion", candidate.finding.get("results_writeup")),
    ]
    lines = [f"# {title}", ""]
    for heading, value in sections:
        lines.extend(
            [
                f"## {heading}",
                "",
                str(value).strip() if value else "Not recorded.",
                "",
            ]
        )
    lines.extend(
        [
            "## Export Provenance",
            "",
            f"- Run ID: `{candidate.run_id}`",
            f"- Idea: `{candidate.idea_name}`",
            f"- Headline: `{candidate.headline_pct:.2f}%`",
            f"- Suite: `{candidate.score.get('suite')}`",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def export_champion(
    team_dir: Path,
    output_dir: Path,
    *,
    expected_suite: str | None = None,
    expected_inference_backend: str | None = None,
    required_artifact_type: str = "either",
    base_model: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Select the champion and atomically create its submission directory."""
    team_dir = team_dir.expanduser().resolve(strict=True)
    output_dir = output_dir.expanduser().absolute()
    if output_dir in {Path("/"), Path.home()}:
        raise ChampionExportError(f"unsafe output directory: {output_dir}")
    if _path_is_within(output_dir, team_dir) or _path_is_within(team_dir, output_dir):
        raise ChampionExportError(
            "output directory must be outside the team directory and must not contain it"
        )
    if output_dir.is_symlink():
        raise ChampionExportError("output directory cannot be a symbolic link")
    champion, candidates = select_champion(
        team_dir,
        expected_suite=expected_suite,
        expected_inference_backend=expected_inference_backend,
        required_artifact_type=required_artifact_type,
    )
    assert champion.model_path is not None
    assert champion.method_path is not None

    if _path_is_within(output_dir, champion.model_path) or _path_is_within(
        output_dir, champion.method_path
    ):
        raise ChampionExportError("output directory cannot be inside a packaged source")
    if output_dir.exists():
        if not force:
            raise ChampionExportError(
                f"output directory already exists (pass --force to replace it): {output_dir}"
            )
        shutil.rmtree(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.incomplete-", dir=output_dir.parent)
    )

    try:
        shutil.copytree(champion.model_path, staging / "model")
        validate_model_submission(str(staging / "model"))
        omitted = _copy_method_source(champion.method_path, staging / "method")
        shutil.copy2(champion.score_path, staging / "score.json")
        assert champion.proposal_path is not None
        shutil.copy2(champion.proposal_path, staging / "proposal.json")
        if champion.finding_path:
            shutil.copy2(champion.finding_path, staging / "finding.json")
        (staging / "method_card.md").write_text(
            _method_card(champion), encoding="utf-8"
        )

        attempt_id = (
            team_dir.parent.parent.name if team_dir.parent.name == "aar_teams" else None
        )
        manifest = {
            "schema_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "attempt_id": attempt_id,
            "team_id": team_dir.name,
            "run_metadata": _attempt_metadata(team_dir),
            "selection": {
                "metric": "headline_pct",
                "direction": "maximize",
                "eligibility": [
                    "passes_filter is true",
                    "passes_regression is not false",
                    "approved per-run proposal and matching method code",
                    "exact evaluated model artifact is present and valid",
                ],
                "tie_break": "earliest proposal timestamp, then lexical run_id",
            },
            "selected": {
                **champion.summary(selected=True),
                "suite": champion.score.get("suite"),
                "inference_backend": champion.score.get("inference_backend"),
                "base_model": _base_model(champion, base_model),
                "model_fingerprint": champion.score.get("model_fingerprint"),
                "code_hash": champion.proposal.get("code_hash"),
            },
            "candidates": [
                candidate.summary(selected=candidate is champion)
                for candidate in sorted(candidates, key=lambda item: item.run_id)
            ],
        }
        _write_json(staging / "champion.json", manifest)
        validation = {
            "ok": True,
            "checks": [
                "authoritative score is filter-valid",
                "proposal is bound to the selected run_id",
                "method source matches the approved code hash",
                "packaged model passes validate_model_submission",
            ],
            "warnings": champion.warnings,
            "omitted_method_files": omitted,
        }
        _write_json(staging / "validation.json", validation)
        _write_json(staging / "checksums.json", package_checksums(staging))
        os.replace(staging, output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest
