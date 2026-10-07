"""Eval entrypoint — runs on the eval side (a Slurm eval job in fs mode, or an
ephemeral RunPod pod in s3 mode).

Lifecycle (transport-agnostic; see aar/transport.py):
  1. get the submitted model        (fs: read SUBMISSIONS_DIR/<run_id>/model in place; s3: download)
  2. resolve the SECRET suite        (fs: HOLDOUT_DIR/<suite>; s3: download from secret prefix)
  3. score the model vs the suite    (run_eval.run)
  4. publish scores.json             (the completion signal the caller polls for)
  5. (s3 only) self-terminate the pod

Invoked as:
    python -m aar.eval_pod.entrypoint --run-id <id> --suite <name>

No item ever leaves this process — only the aggregate scores.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from aar import config, transport
from aar.eval_pod import run_eval
from aar.phase_timing import phase


def _self_terminate() -> None:
    """s3/RunPod mode only — the pod terminates itself after scoring."""
    pod_id = os.getenv("RUNPOD_POD_ID")
    if not pod_id:
        return
    try:
        from aar.infrastructure.runpod import stop_pod
        stop_pod(pod_id)
        print(f"[eval] terminated pod {pod_id}")
    except Exception as e:
        print(f"[eval] self-terminate failed (caller will reap): {e}")


@phase("eval.total")
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--suite", default=config.SUITE_NAME)
    args = ap.parse_args()

    # 1 + 2: obtain model + secret suite (paths; copies only in s3 mode).
    os.environ["AAR_CURRENT_RUN_ID"] = args.run_id
    with phase("eval.model_resolution"):
        model_path = transport.get_model(args.run_id)
        submission_metadata = transport.get_model_submission_metadata(args.run_id)
        override = os.getenv("EVAL_MODEL_PATH_OVERRIDE", "").strip()
        if override:
            override_path = Path(override).resolve()
            if not override_path.is_dir():
                raise RuntimeError(
                    f"EVAL_MODEL_PATH_OVERRIDE is not a directory: {override_path}"
                )
            model_path = str(override_path)
            print(f"[eval] model path override -> {model_path}", flush=True)
    with phase("eval.suite_resolution"):
        suite_dir = transport.resolve_suite_dir(args.suite)
        suite_yaml = Path(suite_dir) / f"{args.suite}.yaml"
        if not suite_yaml.exists():
            suite_yaml = Path(config.SUITE_CONFIG)  # fallback to a bundled config

    # 3: score (write a local scores file first).
    work = Path(config.HARNESS_RUNS_DIR) / "_evalwork" / args.run_id
    work.mkdir(parents=True, exist_ok=True)
    local_scores = work / "scores.json"
    try:
        with phase("eval.scoring"):
            result = run_eval.run(
                str(suite_yaml),
                model_path,
                secret_dir=suite_dir,
                out=str(local_scores),
            )
    except Exception as e:
        result = {"error": str(e)}
        local_scores.write_text(json.dumps(result, indent=2))
        print(f"[eval] scoring failed: {e}", file=sys.stderr)
        if os.getenv("EVAL_FAIL_ON_SCORING_ERROR", "0").lower() in (
            "1", "true", "yes", "on"
        ):
            raise

    # 4: publish scores (completion signal) — HELD-OUT ISOLATION ENFORCED HERE.
    # transport.put_scores writes to the RESEARCH-readable SCORES_DIR (the AAR side
    # polls it, and could `cat` it). So publish the composite with the held-out
    # benchmark STRIPPED; the held-out's score never enters research-readable storage.
    # The FULL composite (incl held-out) is persisted to the eval-private, mode-700
    # HELDOUT_SCORES_DIR (eval-user-owned — the AAR cannot read it); the human reads
    # the generalization score from there with eval credentials.
    from aar.benchmarks.composite import contains_held_out, strip_held_out
    research_result = strip_held_out(result) if isinstance(result, dict) else result
    if submission_metadata is not None:
        if not isinstance(result, dict) or not isinstance(research_result, dict):
            raise RuntimeError("cannot attach model submission metadata to a non-object score")
        result["model_submission"] = submission_metadata
        research_result["model_submission"] = submission_metadata
    with phase("eval.private_result_persistence"):
        if contains_held_out(result):
            try:
                hdir = Path(config.HELDOUT_SCORES_DIR)
                hdir.mkdir(parents=True, exist_ok=True)
                try:
                    os.chmod(hdir, 0o700)
                except OSError:
                    pass
                private_path = hdir / f"{args.run_id}.json"
                private_path.write_text(json.dumps(result, indent=2))
                try:
                    os.chmod(private_path, 0o600)
                except OSError:
                    pass
                print(f"[eval] FULL incl held-out -> {private_path} (eval-private, mode-700)")
            except Exception as e:
                print(f"[eval] WARN: failed to persist eval-private held-out scores: {e}", file=sys.stderr)
                research_result = {
                    "error": "held-out evaluation completed but private result storage failed"
                }
    with phase("eval.score_publication"):
        ref = transport.put_scores(args.run_id, research_result)
    print(f"[eval] published scores (held-out stripped) -> {ref}")

    # 5: s3/pod self-terminate (no-op in fs mode).
    _self_terminate()


if __name__ == "__main__":
    main()
