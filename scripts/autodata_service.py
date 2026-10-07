#!/usr/bin/env python3
"""Serve the durable AAR-facing adapter for a pinned AutoData checkout."""

from __future__ import annotations

import argparse
import json
import importlib.util
import os
import subprocess
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "aar" / "infrastructure" / "autodata_service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("aar_autodata_service", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"cannot load service module at {MODULE_PATH}")
SERVICE_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(SERVICE_MODULE)
AutoDataJobService = SERVICE_MODULE.AutoDataJobService
DeterministicLifecycleBackend = SERVICE_MODULE.DeterministicLifecycleBackend
LiveModelLifecycleBackend = SERVICE_MODULE.LiveModelLifecycleBackend
serve = SERVICE_MODULE.serve


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--pipeline-sha", required=True)
    parser.add_argument(
        "--recipe-root",
        required=True,
        help="Operator-pinned recipe directory contained in the AutoData checkout",
    )
    parser.add_argument(
        "--row-transform",
        choices=("native", "toy_sft"),
        default="native",
        help="Operator-pinned conversion from native dataset items to training rows",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument(
        "--driver-script",
        default=str(Path(__file__).with_name("autodata_unattended_e2e.py")),
    )
    parser.add_argument("--backend", choices=("deterministic", "live"), default="deterministic")
    args = parser.parse_args()
    checkout = Path(args.checkout).resolve()
    actual = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=checkout,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip().lower()
    if actual != args.pipeline_sha.lower():
        raise SystemExit(f"pinned SHA mismatch: expected {args.pipeline_sha}, checkout has {actual}")
    if args.backend == "deterministic":
        backend = DeterministicLifecycleBackend(
            checkout=checkout,
            recipe_root=Path(args.recipe_root),
            driver_script=Path(args.driver_script),
            row_transform=args.row_transform,
        )
    else:
        backend = LiveModelLifecycleBackend(
            driver_script=Path(args.driver_script),
            generator_model=os.getenv("AAR_AUTODATA_GENERATOR_MODEL", ""),
            judge_model=os.getenv("AAR_AUTODATA_JUDGE_MODEL", ""),
            generator_url=os.getenv("AAR_AUTODATA_GENERATOR_URL", ""),
            judge_url=os.getenv("AAR_AUTODATA_JUDGE_URL", ""),
            generator_token_env=os.getenv("AAR_AUTODATA_GENERATOR_TOKEN_ENV", ""),
            judge_token_env=os.getenv("AAR_AUTODATA_JUDGE_TOKEN_ENV", ""),
            generator_deployment_id=os.getenv(
                "AAR_AUTODATA_GENERATOR_DEPLOYMENT_ID", ""
            ),
            max_wall_seconds=int(
                os.getenv("AAR_AUTODATA_MAX_WALL_SECONDS", "10800")
            ),
        )
    controls_json = os.getenv("AAR_AUTODATA_REQUIRED_CONTROLS_JSON", "").strip()
    required_controls = json.loads(controls_json) if controls_json else None
    if required_controls is not None and not isinstance(required_controls, dict):
        raise SystemExit("AAR_AUTODATA_REQUIRED_CONTROLS_JSON must be a JSON object")
    spec_json = os.getenv("AAR_AUTODATA_REQUIRED_SPEC_JSON", "").strip()
    required_spec = json.loads(spec_json) if spec_json else None
    if required_spec is not None and not isinstance(required_spec, dict):
        raise SystemExit("AAR_AUTODATA_REQUIRED_SPEC_JSON must be a JSON object")
    service = AutoDataJobService(
        Path(args.state_root),
        actual,
        backend=backend,
        required_controls=required_controls,
        required_spec=required_spec,
    )
    print(f"[aar-autodata-service] serving {actual} on {args.host}:{args.port}", flush=True)
    serve(
        service,
        host=args.host,
        port=args.port,
        bearer_token=os.getenv("AAR_AUTODATA_TOKEN", ""),
    )


if __name__ == "__main__":
    main()
