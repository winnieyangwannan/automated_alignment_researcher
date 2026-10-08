from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from replication.verify_run8_autodata import APPROVAL_POLICY_SHA256, verify


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


class Run8CompletionVerifierTests(unittest.TestCase):
    def _team(self, root: Path) -> Path:
        team = root / "team"
        for directory in ("logs", "scores", "forum", "autodata"):
            (team / directory).mkdir(parents=True)
        _write(
            team / "logs" / "run_summary.json",
            {
                "sessions": 2,
                "successful_sessions": 2,
                "failed_sessions": 0,
                "stop_reason": "max_iterations",
            },
        )
        scope = "run8-shared-scope"
        for index in range(2):
            run_id = f"run-{index}"
            session_id = f"session_{index:03d}_alpha_20261007_00000{index}"
            (team / "logs" / f"{session_id}.log").write_text(
                "# Result: success=True\n# Ended: now\n"
            )
            rows = [
                {
                    "id": f"{run_id}-{item}",
                    "prompt": f"prompt {item}",
                    "response": f"response {item}",
                }
                for item in range(64)
            ]
            payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
            digest = hashlib.sha256(payload.encode()).hexdigest()
            artifact = team / "autodata" / run_id
            artifact.mkdir()
            (artifact / "autodata_rows.jsonl").write_text(payload)
            manifest = {
                "schema": "aar.autodata.dataset/v1",
                "run_id": run_id,
                "pipeline_sha": "9" * 40,
                "row_count": 64,
                "dataset_sha256": digest,
                "idea_name": f"idea-{index}",
                "training_view": "sft",
                "required_retained_rows": 64,
                "counts": {"generated": 96, "rejected": 32, "retained": 64},
                "method_code_sha256": "1" * 64,
                "autodata_spec_sha256": "2" * 64,
                "resource_profile": "production-v1",
                "resource_profile_sha256": "3" * 64,
                "budget_scope_id": scope,
                "recipe_digest": "4" * 64,
                "pipeline_digest": "5" * 64,
                "workspace_id": f"workspace-{index}",
                "workspace_snapshot_id": f"snapshot-{index}",
                "study_id": f"study-{index}",
                "execution_id": f"production-{index}",
                "meta_optimize_execution_id": f"meta-{index}",
                "production_execution_id": f"production-{index}",
                "meta_optimize_tuning_task_count": 64,
                "meta_optimize_validation_task_count": 32,
                "meta_optimize_source_task_count": 96,
                "production_source_task_count": 96,
                "modes_completed_in_order": ["meta_optimize", "production"],
                "sandoq_executor": "SandoQFirecrackerExecutor",
                "unattended": True,
                "approval_principal": "aar-integrity-monitor",
                "approval_policy_sha256": APPROVAL_POLICY_SHA256,
                "action_provider": "aar-visible-agent-and-integrity-monitor",
                "action_audit": [
                    {
                        "kind": kind,
                        "actor": actor,
                        "result_sha256": "6" * 64,
                    }
                    for kind, actor in (
                        ("clarify_design", "aar-research-agent"),
                        ("author_grounding", "aar-research-agent"),
                        ("approve_grounding", "aar-integrity-monitor"),
                        ("author_pipeline", "aar-research-agent"),
                        ("approve_baseline", "aar-integrity-monitor"),
                    )
                ],
                "models": {
                    "generator": {
                        "identity": "Kimi-K2.6",
                        "deployment_id": "winnieyangwn-kimi26",
                    },
                    "judge": {"identity": "gpt-5-6-luna"},
                },
                "budget": {"model_calls": 200},
            }
            _write(artifact / "autodata_manifest.json", manifest)
            _write(
                artifact / "autodata_consumption.json",
                {
                    "schema": "aar.autodata.consumption/v1",
                    "run_id": run_id,
                    "dataset_sha256": digest,
                    "row_count": 64,
                    "loaded_at_unix": 1,
                    "consumer_pid": 1,
                },
            )
            link = {
                "schema": "aar.autodata.training-link/v1",
                "run_id": run_id,
                "dataset_sha256": digest,
                "row_count": 64,
                "training_view": "sft",
                "consumption_receipt_schema": "aar.autodata.consumption/v1",
            }
            _write(
                artifact / "autodata_training_link.json",
                {**link, "model_submission_ref": f"submission/{run_id}", "submitted_at_unix": 2},
            )
            submission = {
                "schema": "aar.model-submission/v1",
                "run_id": run_id,
                "training_data": link,
            }
            per_benchmark = {
                f"bench-{item}": {"role": "safety" if item < 7 else "capability_filter"}
                for item in range(10)
            }
            score = {
                "suite": "honesty_sycophancy_concealing_uncertainty",
                "headline_pct": 1.0,
                "per_benchmark": per_benchmark,
                "model_submission": submission,
            }
            _write(team / "scores" / f"{run_id}.json", score)
            _write(
                team / "scores" / ".proposals" / "runs" / f"{run_id}.json",
                {
                    "run_id": run_id,
                    "idea_name": f"idea-{index}",
                    "paper": {"title": f"Approved idea {index}"},
                    "proposal_ts": 1,
                    "code_hash": manifest["method_code_sha256"],
                    "autodata_spec_sha256": manifest["autodata_spec_sha256"],
                    "autodata_resource_profile": manifest["resource_profile"],
                    "autodata_resource_profile_sha256": manifest["resource_profile_sha256"],
                    "autodata_budget_scope_id": scope,
                    "autodata_required_retained_rows": "64",
                },
            )
            _write(
                team / "forum" / f"finding-{index}.json",
                {
                    "finding_type": "result",
                    "run_id": run_id,
                    "aar_session_id": session_id,
                    "autodata_dataset_sha256": digest,
                    "composite_scores": {**score, "run_id": run_id, "_authoritative": True},
                },
            )
        return team

    def test_proves_two_sequential_live_autodata_training_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = verify(self._team(Path(temporary)))
            self.assertTrue(result["ok"])
            self.assertEqual(result["verification_schema"], "aar.run8.completion/v1")
            self.assertEqual(
                [item["run_id"] for item in result["autodata"]["runs"]],
                ["run-0", "run-1"],
            )

    def test_rejects_non_native_or_wrong_model_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            team = self._team(Path(temporary))
            path = team / "autodata" / "run-0" / "autodata_manifest.json"
            value = json.loads(path.read_text())
            value["models"]["generator"]["identity"] = "deterministic-template"
            _write(path, value)
            with self.assertRaisesRegex(SystemExit, "generator mismatch"):
                verify(team)

    def test_rejects_dataset_consumption_or_result_digest_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            team = self._team(Path(temporary))
            receipt = team / "autodata" / "run-1" / "autodata_consumption.json"
            value = json.loads(receipt.read_text())
            value["dataset_sha256"] = "f" * 64
            _write(receipt, value)
            with self.assertRaisesRegex(SystemExit, "consumption dataset_sha256 mismatch"):
                verify(team)

    def test_rejects_score_without_submitted_model_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            team = self._team(Path(temporary))
            score = team / "scores" / "run-0.json"
            value = json.loads(score.read_text())
            value.pop("model_submission")
            _write(score, value)
            with self.assertRaisesRegex(SystemExit, "score has no model-submission provenance"):
                verify(team)

    def test_rejects_unrecognized_autonomous_approval_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            team = self._team(Path(temporary))
            path = team / "autodata" / "run-0" / "autodata_manifest.json"
            value = json.loads(path.read_text())
            value["approval_policy_sha256"] = "0" * 64
            _write(path, value)
            with self.assertRaisesRegex(SystemExit, "autonomous approval policy mismatch"):
                verify(team)


if __name__ == "__main__":
    unittest.main()
