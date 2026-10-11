from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from aar.research_loop import autodata_approval
from aar.research_loop import monitor


def _environment(tmp_path: Path) -> dict[str, str]:
    plugin = tmp_path / "plugin"
    artifacts = tmp_path / "artifacts"
    workspaces = tmp_path / "workspaces"
    plugin.mkdir()
    artifacts.mkdir()
    workspaces.mkdir()
    wrapper = plugin / "scripts" / "autodata.py"
    wrapper.parent.mkdir()
    wrapper.write_text("# test wrapper\n", encoding="utf-8")
    state = tmp_path / "state.db"
    state.touch()
    return {
        "AAR_AUTODATA_PLUGIN_ROOT": str(plugin),
        "AAR_AUTODATA_STATE": str(state),
        "AAR_AUTODATA_ARTIFACTS": str(artifacts),
        "AAR_AUTODATA_WORKSPACES": str(workspaces),
        "AAR_AUTODATA_WRAPPER_PYTHON": "/pinned/autodata/python",
    }


def test_run_cli_uses_pinned_wrapper_python(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='{"status":"ok"}\n', stderr=""
    )
    with (
        mock.patch.dict(os.environ, _environment(tmp_path), clear=False),
        mock.patch("subprocess.run", return_value=completed) as run,
    ):
        assert autodata_approval._run_cli(["status", "ws_test"]) == {
            "status": "ok"
        }

    assert run.call_args.args[0][0] == "/pinned/autodata/python"


def test_run_cli_reports_signal_when_stderr_is_empty(tmp_path: Path) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=-9, stdout="", stderr=""
    )
    with (
        mock.patch.dict(os.environ, _environment(tmp_path), clear=False),
        mock.patch("subprocess.run", return_value=completed),
        pytest.raises(RuntimeError, match=r"exit=-9 signal=SIGKILL.*<empty>"),
    ):
        autodata_approval._run_cli(["status", "ws_test"])


def _baseline_package(*, valid: float = 0.0, challenge: float = 0.0) -> dict:
    digest = "sha256:" + "a" * 64
    return {
        "action_kind": "approve_baseline",
        "scope": {"kind": "workspace", "id": "ws_" + "1" * 32},
        "artifact_digests": ["sha256:" + "f" * 64],
        "evidence": [
            {
                "content": {
                    "schema": "autodata.baseline-review/v1",
                    "sample_task_ids": ["sample-sycophancy"],
                    "sample_results": [
                        {
                            "schema": "autodata.task-result/v1",
                            "task_id": "sample-sycophancy",
                            "outcome": "succeeded",
                            "generated_items": [
                                {
                                    "prompt": "Natural prompt",
                                    "response": "Truthful response",
                                    "metadata": {
                                        "axis": "sycophancy_resistance",
                                        "axis_strategy_sha256": digest,
                                        "judge_accepted": valid == 1,
                                        "teacher_accepted": True,
                                        "target_challenging": challenge > 0,
                                        "primary_teacher_dimension": "sycophancy_resistance",
                                        "judge_score": 0.5,
                                        "judge_reason": "bounded diagnostic",
                                        "judge_rubric_version": "rubric-v1",
                                        "judge_rubric_sha256": "sha256:" + "c" * 64,
                                        "target_model": "gemma",
                                        "target_deployment_id": "chain-target",
                                        "target_checkpoint_hash": digest,
                                    },
                                }
                            ],
                            "metrics": {
                                "quality": 0.5,
                                "valid": valid,
                                "challenge": challenge,
                                "quality_challenge_utility": (
                                    2 * 0.5 * challenge / (0.5 + challenge)
                                    if valid == 1 and challenge > 0
                                    else 0.0
                                ),
                            },
                            "provider_usage": [
                                {
                                    "role": "generator",
                                    "request_id": "gen-1",
                                    "model": "Kimi-K2.6",
                                    "deployment_id": "autodata-kimi",
                                },
                                {
                                    "role": "target",
                                    "request_id": "target-1",
                                    "model": "gemma",
                                    "deployment_id": "chain-target",
                                    "checkpoint_hash": digest,
                                },
                                {
                                    "role": "judge",
                                    "request_id": "judge-1",
                                    "model": "gpt-5-6-luna",
                                },
                            ],
                            "reason_code": (
                                None if valid == 1 else "target_not_challenging"
                            ),
                        }
                    ],
                    "mutable_paths": ["recipe/generation_strategy.json"],
                    "protected_paths": [
                        "autodata.pipeline.json",
                        "autodata.workspace.json",
                        "grounding/**",
                        "framework.lock.json",
                        "objective.json",
                        "comparator.json",
                        "schemas/**",
                        "recipe/judge_rubric.json",
                        "recipe/task.py",
                        "recipe/check.py",
                        "recipe/request.json",
                        "training-data-contract.json",
                    ],
                }
            }
        ],
    }


def _set_package_axis(
    package: dict, *, axis: str, task_id: str, strategy_digest: str
) -> dict:
    content = package["evidence"][0]["content"]
    sample = content["sample_results"][0]
    content["sample_task_ids"] = [task_id]
    sample["task_id"] = task_id
    metadata = sample["generated_items"][0]["metadata"]
    metadata["axis"] = axis
    metadata["axis_strategy_sha256"] = strategy_digest
    metadata["primary_teacher_dimension"] = {
        "honesty": "factual_honesty",
        "sycophancy_resistance": "sycophancy_resistance",
        "uncertainty_disclosure": "uncertainty_disclosure",
    }[axis]
    return package


def _action_id(ordinal: int) -> str:
    return "act_" + f"{ordinal:024x}"


def _identity_environment(tmp_path: Path) -> dict[str, str]:
    policy = tmp_path / "campaign-policy.json"
    policy.write_text(
        json.dumps(
            {
                "required_solve_env": {
                    "AUTODATA_GENERATOR_MODEL": "Kimi-K2.6",
                    "AUTODATA_GENERATOR_DEPLOYMENT_ID": "autodata-kimi",
                    "AUTODATA_TARGET_MODEL": "gemma",
                    "AUTODATA_TARGET_DEPLOYMENT_ID": "chain-target",
                    "AUTODATA_TARGET_CHECKPOINT_HASH": "sha256:" + "a" * 64,
                    "AUTODATA_JUDGE_MODEL": "gpt-5-6-luna",
                }
            }
        )
    )
    policy.chmod(0o600)
    return {"AAR_AUTODATA_CAMPAIGN_POLICY": str(policy)}


def test_baseline_is_an_operational_not_content_quality_gate(tmp_path: Path) -> None:
    # A rejected, non-challenging sample is still sufficient to start native
    # meta-optimization when execution/schema/provenance controls are intact.
    with mock.patch.dict(os.environ, _identity_environment(tmp_path), clear=False):
        autodata_approval._deterministic_checks(
            _baseline_package(valid=0.0, challenge=0.0)
        )
    verdict = autodata_approval._baseline_operational_verdict(
        _baseline_package(valid=0.0, challenge=0.0)
    )
    assert verdict["approved"] is True
    assert verdict["monitor_backend"] == "local"
    assert "0/1" in verdict["feedback"]


def test_baseline_operational_gate_fails_closed_on_missing_role_provenance(
    tmp_path: Path,
) -> None:
    package = _baseline_package()
    sample = package["evidence"][0]["content"]["sample_results"][0]
    sample["provider_usage"] = [
        entry for entry in sample["provider_usage"] if entry["role"] != "target"
    ]
    with mock.patch.dict(os.environ, _identity_environment(tmp_path), clear=False):
        with pytest.raises(RuntimeError, match="generator, target, and judge"):
            autodata_approval._deterministic_checks(package)


def test_baseline_operational_gate_requires_trusted_runtime_identity() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="trusted campaign policy identity"):
            autodata_approval._deterministic_checks(_baseline_package())


def test_baseline_operational_gate_requires_one_diagnostic_item(
    tmp_path: Path,
) -> None:
    package = _baseline_package()
    package["evidence"][0]["content"]["sample_results"][0][
        "generated_items"
    ] = []
    with mock.patch.dict(os.environ, _identity_environment(tmp_path), clear=False):
        with pytest.raises(RuntimeError, match="exactly one diagnostic item"):
            autodata_approval._deterministic_checks(package)


def test_baseline_operational_gate_accepts_teacher_and_target_both_failing(
    tmp_path: Path,
) -> None:
    package = _baseline_package(valid=0.0, challenge=0.0)
    sample = package["evidence"][0]["content"]["sample_results"][0]
    metadata = sample["generated_items"][0]["metadata"]
    metadata["teacher_accepted"] = False
    sample["reason_code"] = "judge_rejected"
    with mock.patch.dict(os.environ, _identity_environment(tmp_path), clear=False):
        autodata_approval._deterministic_checks(package)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("schema", "task-result schema"),
        ("utility", "bounded finite"),
        ("duplicate_request", "request ids are not unique"),
        ("spoof_roles", "reuse a spoofed identity"),
        ("contradictory", "challenge evidence is contradictory"),
        ("duplicate_sample", "task identities are inconsistent"),
        ("extra_artifact", "exactly one evidence artifact"),
        ("protected", "does not protect scientific controls"),
    ],
)
def test_baseline_operational_gate_rejects_inconsistent_evidence(
    tmp_path: Path, mutation: str, error: str
) -> None:
    package = _baseline_package(valid=1.0, challenge=1.0)
    content = package["evidence"][0]["content"]
    sample = content["sample_results"][0]
    metadata = sample["generated_items"][0]["metadata"]
    if mutation == "schema":
        sample["schema"] = "wrong"
    elif mutation == "utility":
        sample["metrics"]["quality_challenge_utility"] = float("nan")
    elif mutation == "duplicate_request":
        sample["provider_usage"][1]["request_id"] = sample["provider_usage"][0][
            "request_id"
        ]
    elif mutation == "spoof_roles":
        sample["provider_usage"][1]["model"] = sample["provider_usage"][0][
            "model"
        ]
    elif mutation == "contradictory":
        metadata["target_challenging"] = False
    elif mutation == "duplicate_sample":
        content["sample_results"].append(copy.deepcopy(sample))
    elif mutation == "extra_artifact":
        package["evidence"].append(copy.deepcopy(package["evidence"][0]))
        package["artifact_digests"].append("sha256:" + "e" * 64)
    else:
        content["protected_paths"].remove("training-data-contract.json")
    with mock.patch.dict(os.environ, _identity_environment(tmp_path), clear=False):
        with pytest.raises(RuntimeError, match=error):
            autodata_approval._deterministic_checks(package)


def test_delegated_baseline_policy_does_not_require_content_acceptance() -> None:
    assert "OPERATIONAL gate" in monitor._AUTODATA_APPROVAL_PROMPT
    assert "do not require valid=1" in monitor._AUTODATA_APPROVAL_PROMPT
    assert "production export remains strict" in monitor._AUTODATA_APPROVAL_PROMPT


def test_axis_incumbent_reuses_same_digest_and_invalidates_only_changed_axis(
    tmp_path: Path,
) -> None:
    environment = {
        "AAR_AUTODATA_APPROVAL_AUDIT_DIR": str(tmp_path),
        **_identity_environment(tmp_path),
    }
    accepted = _baseline_package(valid=1.0, challenge=1.0)
    with mock.patch.dict(os.environ, environment, clear=False):
        first = autodata_approval._update_axis_incumbents(
            accepted, action_id=_action_id(1)
        )
        assert first["updated_axes"] == ["sycophancy_resistance"]
        assert first["active_axes"] == ["sycophancy_resistance"]

        honesty = _set_package_axis(
            _baseline_package(valid=1.0, challenge=1.0),
            axis="honesty",
            task_id="sample-honesty",
            strategy_digest="sha256:" + "d" * 64,
        )
        second = autodata_approval._update_axis_incumbents(
            honesty, action_id=_action_id(2)
        )
        assert second["updated_axes"] == ["honesty"]
        assert second["active_axes"] == ["honesty", "sycophancy_resistance"]

        same_digest_rejection = _baseline_package(valid=0.0, challenge=0.0)
        retained = autodata_approval._update_axis_incumbents(
            same_digest_rejection, action_id=_action_id(3)
        )
        assert retained["retained_axes"] == ["sycophancy_resistance"]
        assert retained["active_axes"] == ["honesty", "sycophancy_resistance"]

        changed_digest_rejection = _baseline_package(valid=0.0, challenge=0.0)
        metadata = changed_digest_rejection["evidence"][0]["content"][
            "sample_results"
        ][0]["generated_items"][0]["metadata"]
        metadata["axis_strategy_sha256"] = "sha256:" + "b" * 64
        invalidated = autodata_approval._update_axis_incumbents(
            changed_digest_rejection, action_id=_action_id(4)
        )
        assert invalidated["invalidated_axes"] == ["sycophancy_resistance"]
        assert invalidated["active_axes"] == ["honesty"]

    state_path = tmp_path / (
        "ws_" + "1" * 32 + "-baseline-axis-incumbents.json"
    )
    assert state_path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "changed_binding",
    ["target_checkpoint", "rubric_sha256", "generator_deployment"],
)
def test_axis_incumbent_invalidates_on_model_or_rubric_binding_change(
    tmp_path: Path, changed_binding: str
) -> None:
    audit = tmp_path / changed_binding
    audit.mkdir()
    audit.chmod(0o700)
    environment = {
        "AAR_AUTODATA_APPROVAL_AUDIT_DIR": str(audit),
        **_identity_environment(audit),
    }
    accepted = _baseline_package(valid=1.0, challenge=1.0)
    honesty = _set_package_axis(
        _baseline_package(valid=1.0, challenge=1.0),
        axis="honesty",
        task_id="sample-honesty",
        strategy_digest="sha256:" + "d" * 64,
    )
    changed = _baseline_package(valid=0.0, challenge=0.0)
    sample = changed["evidence"][0]["content"]["sample_results"][0]
    metadata = sample["generated_items"][0]["metadata"]
    if changed_binding == "target_checkpoint":
        new_checkpoint = "sha256:" + "e" * 64
        metadata["target_checkpoint_hash"] = new_checkpoint
        next(
            entry for entry in sample["provider_usage"] if entry["role"] == "target"
        )["checkpoint_hash"] = new_checkpoint
    elif changed_binding == "rubric_sha256":
        metadata["judge_rubric_sha256"] = "sha256:" + "e" * 64
    else:
        next(
            entry
            for entry in sample["provider_usage"]
            if entry["role"] == "generator"
        )["deployment_id"] = "autodata-kimi-restarted"

    with mock.patch.dict(os.environ, environment, clear=False):
        autodata_approval._deterministic_checks(accepted)
        autodata_approval._deterministic_checks(honesty)
        autodata_approval._update_axis_incumbents(
            accepted, action_id=_action_id(1)
        )
        autodata_approval._update_axis_incumbents(
            honesty, action_id=_action_id(2)
        )
        if changed_binding in {"target_checkpoint", "generator_deployment"}:
            policy_path = Path(environment["AAR_AUTODATA_CAMPAIGN_POLICY"])
            policy = json.loads(policy_path.read_text())
            solve_env = policy["required_solve_env"]
            if changed_binding == "target_checkpoint":
                solve_env["AUTODATA_TARGET_CHECKPOINT_HASH"] = new_checkpoint
            else:
                solve_env[
                    "AUTODATA_GENERATOR_DEPLOYMENT_ID"
                ] = "autodata-kimi-restarted"
            policy_path.write_text(json.dumps(policy))
            policy_path.chmod(0o600)
        autodata_approval._deterministic_checks(changed)
        result = autodata_approval._update_axis_incumbents(
            changed, action_id=_action_id(3)
        )

    assert result["invalidated_axes"] == [
        "honesty",
        "sycophancy_resistance",
    ]
    assert result["active_axes"] == []


def test_incumbent_commit_is_idempotent_and_replay_bound(tmp_path: Path) -> None:
    environment = {
        "AAR_AUTODATA_APPROVAL_AUDIT_DIR": str(tmp_path),
        **_identity_environment(tmp_path),
    }
    package = _baseline_package(valid=1.0, challenge=1.0)
    action_id = _action_id(10)
    with mock.patch.dict(os.environ, environment, clear=False):
        first = autodata_approval._update_axis_incumbents(
            package, action_id=action_id
        )
        state_path = tmp_path / (
            "ws_" + "1" * 32 + "-baseline-axis-incumbents.json"
        )
        first_bytes = state_path.read_bytes()
        replay = autodata_approval._update_axis_incumbents(
            package, action_id=action_id
        )
        assert replay == first
        assert state_path.read_bytes() == first_bytes

        changed = _baseline_package(valid=0.0, challenge=0.0)
        with pytest.raises(RuntimeError, match="replay changed"):
            autodata_approval._update_axis_incumbents(
                changed, action_id=action_id
            )


def test_incumbent_commit_rejects_malformed_nested_state(tmp_path: Path) -> None:
    environment = {
        "AAR_AUTODATA_APPROVAL_AUDIT_DIR": str(tmp_path),
        **_identity_environment(tmp_path),
    }
    package = _baseline_package(valid=1.0, challenge=1.0)
    with mock.patch.dict(os.environ, environment, clear=False):
        autodata_approval._update_axis_incumbents(
            package, action_id=_action_id(1)
        )
        state_path = tmp_path / (
            "ws_" + "1" * 32 + "-baseline-axis-incumbents.json"
        )
        state = json.loads(state_path.read_text())
        state["axes"]["sycophancy_resistance"].pop("result_sha256")
        state_path.write_text(json.dumps(state))
        state_path.chmod(0o600)
        with pytest.raises(RuntimeError, match="axis record is invalid"):
            autodata_approval._update_axis_incumbents(
                package, action_id=_action_id(2)
            )


def test_failed_binding_or_native_completion_does_not_mutate_incumbents(
    tmp_path: Path,
) -> None:
    action_id = _action_id(20)
    action = {
        "id": action_id,
        "kind": "approve_baseline",
        "scope": {"kind": "workspace", "id": "ws_" + "1" * 32},
        "artifacts": [],
    }
    package = _baseline_package(valid=0.0, challenge=0.0)
    dummy = tmp_path / "dummy"
    dummy.write_text("x")
    environment = {
        "AAR_AUTODATA_APPROVAL_AUDIT_DIR": str(tmp_path),
        **_identity_environment(tmp_path),
    }
    with (
        mock.patch.dict(os.environ, environment, clear=False),
        mock.patch.object(autodata_approval, "_required_path", return_value=dummy),
        mock.patch.object(
            autodata_approval,
            "_action_row",
            return_value={"status": "pending", "specJson": json.dumps(action)},
        ),
        mock.patch.object(
            autodata_approval, "_review_package", return_value=package
        ),
        mock.patch.object(
            autodata_approval,
            "_proposal_binding",
            side_effect=RuntimeError("binding failed"),
        ),
        mock.patch.object(autodata_approval, "_sign", return_value="signature"),
        mock.patch.object(autodata_approval, "_update_axis_incumbents") as update,
        pytest.raises(RuntimeError, match="binding failed"),
    ):
        autodata_approval.review_and_complete_action(action_id)
    update.assert_not_called()

    with (
        mock.patch.dict(os.environ, environment, clear=False),
        mock.patch.object(autodata_approval, "_required_path", return_value=dummy),
        mock.patch.object(
            autodata_approval,
            "_action_row",
            return_value={"status": "pending", "specJson": json.dumps(action)},
        ),
        mock.patch.object(
            autodata_approval, "_review_package", return_value=package
        ),
        mock.patch.object(
            autodata_approval, "_proposal_binding", return_value={"bound": True}
        ),
        mock.patch.object(autodata_approval, "_sign", return_value="signature"),
        mock.patch.object(
            autodata_approval,
            "_run_cli",
            side_effect=[{"lease_token": "lease"}, RuntimeError("complete failed")],
        ),
        mock.patch.object(autodata_approval, "_update_axis_incumbents") as update,
        pytest.raises(RuntimeError, match="complete failed"),
    ):
        autodata_approval.review_and_complete_action(action_id)
    update.assert_not_called()
