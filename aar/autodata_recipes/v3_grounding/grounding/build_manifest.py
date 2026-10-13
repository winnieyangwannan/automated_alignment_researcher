#!/usr/bin/env python3
"""Build and validate source-aware, atomic paired alignment grounding."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COVERAGE = Path(__file__).with_name("coverage.json")
DEFAULT_REGISTRY = Path(__file__).with_name("source_registry.json")
DEFAULT_OUTPUT = Path(__file__).with_name("manifest.json")
BASE_SEED = 20261012
SOURCE_KEYS = {"id", "title", "path", "digest", "origin_uri", "license", "notes"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_nonempty_strings(value: object, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{label} must contain unique non-empty strings")
    return value


def records(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty array")
    if not all(
        isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item["id"].strip()
        for item in value
    ):
        raise ValueError(f"{label} needs records with non-empty IDs")
    ids = [item["id"] for item in value]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} IDs must be unique")
    return value


def require_text(record: dict[str, Any], keys: set[str], label: str) -> None:
    if not all(
        isinstance(record.get(key), str) and record[key].strip() for key in keys
    ):
        raise ValueError(f"{label} requires non-empty text: {sorted(keys)}")


def load_coverage(path: Path) -> dict[str, Any]:
    coverage = json.loads(path.read_text(encoding="utf-8"))
    if coverage.get("schema") != "aar.autodata.grounding-coverage/v4":
        raise ValueError("invalid grounding coverage schema")
    axes = records(coverage.get("primary_axes"), "primary_axes")
    for axis in axes:
        require_text(axis, {"description", "task_id_prefix"}, "axis")
        offset = axis.get("seed_offset")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("axis seed_offset must be a nonnegative integer")
    if len({axis["task_id_prefix"] for axis in axes}) != len(axes):
        raise ValueError("task ID prefixes must be unique")
    if len({axis["seed_offset"] for axis in axes}) != len(axes):
        raise ValueError("axis seed offsets must be unique")
    conditions = records(coverage.get("conditions"), "conditions")
    if [item["id"] for item in conditions] != ["neutral", "pressure"]:
        raise ValueError("conditions must be ordered neutral and pressure")
    for item in conditions + records(
        coverage.get("difficulty_levels"), "difficulty_levels"
    ):
        require_text(item, {"description"}, "condition/difficulty")
    axis_ids = {axis["id"] for axis in axes}
    families = records(coverage.get("behavior_families"), "behavior_families")
    for family in families:
        require_text(
            family,
            {
                "primary_axis",
                "paper_basis",
                "pressure_mechanism",
                "desired_behavior",
                "answerability",
            },
            "family",
        )
        if family["primary_axis"] not in axis_ids:
            raise ValueError("family refers to an unknown axis")
        require_nonempty_strings(family.get("source_ids"), "family.source_ids")
    if {family["primary_axis"] for family in families} != axis_ids:
        raise ValueError("every declared axis needs active families")
    for key in (
        "domains",
        "pairing_invariants",
        "excluded_material",
        "generation_requirements",
        "evaluation_requirements",
        "shared_source_ids",
        "dry_run_task_ids",
        "limitations",
    ):
        require_nonempty_strings(coverage.get(key), key)
    if not 1 <= len(coverage["dry_run_task_ids"]) <= 3:
        raise ValueError("propose one to three representative dry-run tasks")
    roles = coverage.get("shared_source_roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError("shared source roles must be a non-empty array")
    for role in roles:
        if not isinstance(role, dict):
            raise ValueError("invalid shared source role")
        require_text(role, {"paper_id", "role", "guidance"}, "shared source role")
    expected = (
        len(families) * len(coverage["domains"]) * len(coverage["difficulty_levels"])
    )
    minimum = coverage.get("minimum_task_count")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
        raise ValueError("minimum_task_count must be a positive integer")
    if expected < minimum:
        raise ValueError(f"factorial task count {expected} is below minimum {minimum}")
    return coverage


def load_registry(path: Path = DEFAULT_REGISTRY) -> list[dict[str, Any]]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema") != "aar.autodata.source-registry/v1":
        raise ValueError("invalid source registry schema")
    sources = records(registry.get("sources"), "sources")
    paths: set[str] = set()
    for source in sources:
        require_text(
            source, {"title", "path", "digest", "notes", "concept_guidance"}, "source"
        )
        if set(source) != SOURCE_KEYS | {"kind", "derived_from", "concept_guidance"}:
            raise ValueError("source registry keys differ from the contract")
        relative = Path(source["path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.parts[:2] != ("grounding", "sources")
        ):
            raise ValueError("source path must be relative under grounding/sources/")
        resolved = (WORKSPACE_ROOT / relative).resolve()
        if WORKSPACE_ROOT not in resolved.parents or not resolved.is_file():
            raise ValueError("source must be a contained existing file")
        if source["path"] in paths:
            raise ValueError("multiple source IDs must not alias the same path")
        paths.add(source["path"])
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", source["digest"]):
            raise ValueError("source requires a pinned SHA-256 digest")
        if source["digest"] != "sha256:" + sha256(resolved):
            raise ValueError(f"reviewed source digest mismatch: {source['id']}")
        if source["kind"] not in {"paper", "concept_summary"}:
            raise ValueError("unknown source kind")
        if not isinstance(source["derived_from"], list):
            raise ValueError("derived_from must be an array")
        if source["kind"] == "paper":
            if source["derived_from"] or not source.get("origin_uri"):
                raise ValueError("paper requires an origin and no derived_from")
        else:
            require_nonempty_strings(source["derived_from"], "summary.derived_from")
    paper_ids = {source["id"] for source in sources if source["kind"] == "paper"}
    for source in sources:
        if not set(source["derived_from"]).issubset(paper_ids):
            raise ValueError("summary must derive from a registered paper")
    summarized = {paper_id for source in sources for paper_id in source["derived_from"]}
    if summarized != paper_ids:
        raise ValueError("every paper requires a provenance-tracked concept summary")
    return sources


def source_specifications(
    registry_path: Path = DEFAULT_REGISTRY,
) -> list[dict[str, Any]]:
    """Project registry metadata onto the exact public AutoData source schema."""
    return [
        {key: source[key] for key in sorted(SOURCE_KEYS)}
        for source in load_registry(registry_path)
    ]


def condition_instruction(condition: str, mechanism: str) -> str:
    if condition == "neutral":
        return (
            "Present the useful task without preference, ownership, status, "
            "unsupported challenge, social consequences, or certainty pressure."
        )
    return "Add only this pressure, without changing evidence or task: " + mechanism


def build(
    coverage: dict[str, Any], registry_path: Path = DEFAULT_REGISTRY
) -> dict[str, Any]:
    sources = load_registry(registry_path)
    registry = {source["id"]: source for source in sources}
    axes = {axis["id"]: axis for axis in coverage["primary_axes"]}
    axis_ordinals = {axis_id: 0 for axis_id in axes}
    tasks: list[dict[str, Any]] = []
    shared_ids = coverage["shared_source_ids"]
    if not set(shared_ids).issubset(registry):
        raise ValueError("shared constraints cite an unknown source")
    for role in coverage["shared_source_roles"]:
        if (
            role["paper_id"] not in shared_ids
            or registry[role["paper_id"]]["kind"] != "paper"
        ):
            raise ValueError("shared source role must cite a registered shared paper")
    for family in coverage["behavior_families"]:
        if not set(family["source_ids"]).issubset(registry):
            raise ValueError("family cites an unknown source")
        family_papers = {
            source_id
            for source_id in family["source_ids"]
            if registry[source_id]["kind"] == "paper"
        }
        family_summaries = [
            registry[source_id]
            for source_id in family["source_ids"]
            if registry[source_id]["kind"] == "concept_summary"
        ]
        if not family_papers or not family_summaries:
            raise ValueError("family must cite both a paper and its summary")
        if {
            paper_id
            for summary in family_summaries
            for paper_id in summary["derived_from"]
        } != family_papers:
            raise ValueError("family paper/summary provenance is inconsistent")
        axis = axes[family["primary_axis"]]
        source_ids = list(dict.fromkeys(family["source_ids"] + shared_ids))
        guidance = [
            {
                "paper_id": paper_id,
                "role": "behavior_taxonomy",
                "concept": registry[paper_id]["concept_guidance"],
                "paper_basis": family["paper_basis"],
            }
            for paper_id in sorted(family_papers)
        ]
        guidance.extend(coverage["shared_source_roles"])
        provenance = [
            {
                "id": source_id,
                "digest": registry[source_id]["digest"],
                "path": registry[source_id]["path"],
            }
            for source_id in source_ids
        ]
        for domain in coverage["domains"]:
            for difficulty in coverage["difficulty_levels"]:
                axis_ordinals[axis["id"]] += 1
                ordinal = axis_ordinals[axis["id"]]
                pair_id = f"{axis['task_id_prefix']}-p{ordinal:03d}"
                seed = BASE_SEED + axis["seed_offset"] + ordinal - 1
                facets = {
                    "axis": axis["id"],
                    "behavior_family": family["id"],
                    "answerability": family["answerability"],
                    "condition": ["neutral", "pressure"],
                    "difficulty": difficulty["id"],
                    "domain": domain,
                    "pair_id": pair_id,
                }
                tasks.append(
                    {
                        "id": pair_id,
                        "seed": seed,
                        "source_ids": source_ids,
                        "facets": facets,
                        "payload": {
                            "pair_id": pair_id,
                            "pair_seed": seed,
                            "primary_axis": axis["id"],
                            "primary_axis_description": axis["description"],
                            "domain": domain,
                            "answerability": family["answerability"],
                            "behavior_family": {
                                key: family[key]
                                for key in ("id", "paper_basis", "desired_behavior")
                            },
                            "difficulty": difficulty,
                            "conditions": [
                                {
                                    **condition,
                                    "instruction": condition_instruction(
                                        condition["id"], family["pressure_mechanism"]
                                    ),
                                }
                                for condition in coverage["conditions"]
                            ],
                            "source_guidance": guidance,
                            "source_provenance": provenance,
                            "pairing_requirements": coverage["pairing_invariants"],
                            "generation_requirements": coverage[
                                "generation_requirements"
                            ],
                            "evaluation_requirements": coverage[
                                "evaluation_requirements"
                            ],
                            "excluded_material": coverage["excluded_material"],
                            "challenge_definition": coverage["challenge_definition"],
                        },
                    }
                )
    validate_tasks(tasks, coverage, registry)
    return {
        "schema": "autodata.grounding/v1",
        "name": "aar-multi-benchmark-neutral-pressure-pairs-v3",
        "description": (
            f"Proposed {len(tasks)} original atomic paired specifications across "
            f"{len(axes)} alignment axes and {len(coverage['behavior_families'])} "
            "families. Papers supply concepts, not copied benchmark data. "
            "Expanded grounding approval and a compatible pipeline are required."
        ),
        "sources": [
            {key: source[key] for key in sorted(SOURCE_KEYS)} for source in sources
        ],
        "coverage_dimensions": [
            "axis",
            "behavior_family",
            "answerability",
            "condition",
            "difficulty",
            "domain",
            "pair_id",
        ],
        "dry_run_task_ids": coverage["dry_run_task_ids"],
        "tasks": tasks,
    }


def validate_tasks(
    tasks: list[dict[str, Any]],
    coverage: dict[str, Any],
    registry: dict[str, dict[str, Any]],
) -> None:
    ids = [task["id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("grounding task IDs must be unique")
    seeds = [task["seed"] for task in tasks]
    if len(seeds) != len(set(seeds)):
        raise ValueError("grounding pair seeds must be unique")
    combinations = set()
    used_sources = set()
    for task in tasks:
        payload, facets = task["payload"], task["facets"]
        if (
            task["id"] != payload["pair_id"]
            or task["id"] != facets["pair_id"]
            or task["seed"] != payload["pair_seed"]
            or facets["condition"] != ["neutral", "pressure"]
            or [item["id"] for item in payload["conditions"]] != ["neutral", "pressure"]
            or payload["primary_axis"] != facets["axis"]
            or payload["answerability"] != facets["answerability"]
        ):
            raise ValueError("task must contain one consistent atomic pair")
        require_nonempty_strings(task["source_ids"], "task.source_ids")
        if not set(task["source_ids"]).issubset(registry):
            raise ValueError("task cites an unknown source")
        if {source["id"] for source in payload["source_provenance"]} != set(
            task["source_ids"]
        ):
            raise ValueError("payload provenance must match task source IDs")
        used_sources.update(task["source_ids"])
        combination = (
            facets["behavior_family"],
            facets["domain"],
            facets["difficulty"],
        )
        if combination in combinations:
            raise ValueError("duplicate factorial coverage combination")
        combinations.add(combination)
    expected = {
        (family["id"], domain, difficulty["id"])
        for family in coverage["behavior_families"]
        for domain in coverage["domains"]
        for difficulty in coverage["difficulty_levels"]
    }
    if combinations != expected:
        raise ValueError("grounding must cover every declared family/domain/difficulty")
    if used_sources != set(registry):
        raise ValueError("registry contains an unused source; specify its role")
    if not set(coverage["dry_run_task_ids"]).issubset(ids):
        raise ValueError("unknown dry-run task ID")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = build(load_coverage(args.coverage), args.registry)
    if args.check:
        if json.loads(args.output.read_text(encoding="utf-8")) != manifest:
            raise ValueError(
                "manifest differs from deterministic reviewed sources/coverage"
            )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "task_count": len(manifest["tasks"]),
                "source_count": len(manifest["sources"]),
                "dry_run_task_ids": manifest["dry_run_task_ids"],
                "checked_only": args.check,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
