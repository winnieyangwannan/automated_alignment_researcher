"""Static safety and topology checks for the production Run 8 launchers."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "dishonest_sycophancy_concealing"
    / "run_8"
)
SUBMIT = ROOT / "submit_run_8.sh"
PIPELINE = ROOT / "run_8_pipeline.sbatch"
SERVICES = ROOT / "run_8_autodata_services.sbatch"
REPO = ROOT.parents[2]
RUNTIME_ENV = REPO / "scripts" / "aar_runtime_env.sh"
LAUNCH_TEAM = REPO / "scripts" / "launch_team.sh"
CHAIN = REPO / "scripts" / "slurm_aar_chain.sh"
BWRAP = REPO / "scripts" / "claude_research_bwrap.sh"


def _sources() -> tuple[str, str, str]:
    return SUBMIT.read_text(), PIPELINE.read_text(), SERVICES.read_text()


def test_shell_syntax() -> None:
    for path in (
        SUBMIT,
        PIPELINE,
        SERVICES,
        RUNTIME_ENV,
        LAUNCH_TEAM,
        CHAIN,
        BWRAP,
    ):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_exact_chain_and_evaluator_topology() -> None:
    _, pipeline, _ = _sources()
    assert 'launch_team.sh" "alpha" 2 167' in pipeline
    assert "export AAR_EVAL_WORKERS=1" in pipeline
    assert "export AAR_EVAL_GPUS=4" in pipeline
    assert "export AAR_VERIFY_TWO_ITERATION_ARTIFACTS=1" in pipeline
    assert "export AAR_VERIFY_RUN8_AUTODATA=1" in pipeline
    assert "export AAR_AUTODATA_TRAINING_VIEW=sft" in pipeline
    assert "docker.io/vllm/vllm-openai:v0.25.1" in pipeline
    assert "EVAL_VLLM_LORA_STRATEGY=merged_checkpoint" in pipeline


def test_live_autodata_is_fail_closed() -> None:
    _, pipeline, services = _sources()
    combined = pipeline + services
    assert "export AAR_AUTODATA_REQUIRED=1" in pipeline
    assert "AAR_AUTODATA_REQUIRED_CONTROLS_JSON" in services
    assert "AAR_AUTODATA_REQUIRED_SPEC_JSON" in services
    assert "export AAR_AUTODATA_CONTRACT_SMOKE=0" in pipeline
    assert "--backend live" in services
    assert "-m autodata.broker.cli serve" in services
    assert "--execsidecar-token-file" in services
    assert "--auth-token-file" in services
    assert "--workload-env-file" in services
    assert "--max-concurrent 4" in services
    assert "--backend deterministic" not in combined
    assert "programmatic_contract_smoke" not in combined


def test_models_budget_and_secrets_are_pinned() -> None:
    submit, pipeline, services = _sources()
    combined = submit + pipeline + services
    assert "winnieyangwn-kimi26" in combined
    assert "Kimi-K2.6" in combined
    assert "gpt-5-6-luna" in combined
    assert "AAR_AUTODATA_BUDGET_SCOPE_ID" in pipeline
    assert "AAR_AUTODATA_TOKEN_FILE" in pipeline
    assert "require_mode_0600" in submit
    assert "requires HARNESS_ENV inside /storage/home/${USER}" in submit
    assert "AUTODATA_MAX_COST_USD=100" in submit
    assert "AUTODATA_REQUIRED_RETAINED_ROWS=64" in submit
    assert "AUTODATA_MAX_ESTIMATED_COST_PER_TASK_USD:-0.05" in submit
    assert "AAR_RUN8_GENERATOR_INPUT_USD_PER_MILLION:-1" in submit
    assert "AAR_RUN8_GENERATOR_OUTPUT_USD_PER_MILLION:-4" in submit
    assert "AAR_RUN8_JUDGE_INPUT_USD_PER_MILLION:-1" in submit
    assert "AAR_RUN8_JUDGE_OUTPUT_USD_PER_MILLION:-4" in submit
    assert (
        "EXECSIDECAR_TOKEN_FILE=/storage/home/winnieyangwn/aar-worktrees/"
        "autodata/.sandoq-firecracker-token"
    ) in submit
    assert (
        "/storage/home/winnieyangwn/ram_common/sandoq_fleet/"
        ".venv-x86_64/bin/python"
    ) in submit
    assert (
        "https://ram-inference-gateway.ingress.fair-cw-use2-1.cw.metafb.cloud/v1"
        in submit
    )
    assert "--broker-auth-token-file" in services
    assert "native_broker_canary.json" in services
    model_canary = services.index("autodata_model_broker_canary.py")
    assert services.index("native_broker_canary.json") < model_canary
    assert "model_broker_canary.json" in services
    assert model_canary < services.index('setsid bash "$0" --adapter-child')
    assert 'MODEL_API_KEY="${MODEL_API_KEY}' not in submit
    assert "SANDOQ_AUTH_TOKEN=" not in combined


def test_new_run_artifacts_are_confined_to_user_storage() -> None:
    submit, pipeline, services = _sources()
    combined = submit + pipeline + services
    assert 'RUN8_STORAGE_ROOT="${AAR_RUN8_STORAGE_ROOT:-/storage/home/${USER:?}/aar-runs}"' in submit
    assert 'artifact_base="${RUN8_STORAGE_ROOT}/' in submit
    assert 'attempt_parent="${artifact_base}/run8_attempts"' in submit
    assert 'must stay inside /storage/home/${USER}/aar-runs' in submit
    assert "refuses to store new artifacts under /checkpoint/ram" in submit
    assert 'attempt_parent="/checkpoint/ram' not in submit
    assert 'refuses a symlink artifact base' in submit
    assert 'refuses a symlink attempt parent' in submit
    assert 'AAR_RUNTIME_ROOT="${ATTEMPT_DIR}"' in pipeline
    assert '"${ATTEMPT_DIR}/services/' in services
    assert '"/storage/home/${USER:?}/aar-runs/"*' in pipeline
    assert '"/storage/home/${USER:?}/aar-runs/"*' in services
    assert 'export TMPDIR="${ATTEMPT_DIR}/tmp"' in pipeline
    assert 'export TMPDIR="${ATTEMPT_DIR}/tmp"' in services


def test_checkpoint_inputs_are_never_used_as_run8_write_targets() -> None:
    _, pipeline, _ = _sources()
    launcher = LAUNCH_TEAM.read_text()
    prompt = (REPO / "aar" / "research_loop" / "prompt_safety.jinja2").read_text()

    assert "export AAR_LIT_AXIS_READ_ONLY=1" in pipeline
    assert 'if [ "${AAR_LIT_AXIS_READ_ONLY:-0}" = "1" ]' in launcher
    assert "immutable literature baseline is not ready" in launcher
    assert "/tmp/run_id_current" not in prompt
    assert "/tmp/jobid_" not in prompt
    assert '$TEAM_DIR/logs/run_id_current' in prompt


def test_research_chain_uses_positive_slurm_environment_allowlist() -> None:
    _, pipeline, _ = _sources()
    runtime = RUNTIME_ENV.read_text()
    launcher = LAUNCH_TEAM.read_text()
    chain = CHAIN.read_text()

    assert "export AAR_CHAIN_SANITIZE_ENV=1" in pipeline
    assert "export AAR_RUNTIME_ENV_DISABLE_FILE=1" in pipeline
    assert "export AAR_RESEARCH_ENV_ISOLATION=1" in pipeline
    assert "AAR_MONITOR_MODEL_API_KEY=" in pipeline
    assert "AAR_RESEARCH_CHAIN_ENV_ALLOWLIST=()" in runtime
    assert "HARNESS_ENV|ANTHROPIC_API_KEY|" in runtime
    assert '_chain_export_args=(--export="${_chain_export_csv}")' in launcher
    assert '"${_chain_export_args[@]}"' in launcher
    assert '_chain_export_args=(--export="ALL,' not in launcher
    assert "unset ANTHROPIC_API_KEY" in chain
    assert "AAR_RUN8_EXECSIDECAR_TOKEN_FILE" in chain
    assert "AAR_RUN8_BROKER_TOKEN_FILE" in chain
    assert "claude_research_bwrap.sh" in chain
    assert "--unshare-pid" in BWRAP.read_text()
    assert 'for hidden_root in "${hidden_roots[@]}"' in BWRAP.read_text()
    assert 'bwrap_args+=(--tmpfs "${hidden_root}")' in BWRAP.read_text()


def test_bwrap_hides_home_and_run_secrets_but_keeps_workspaces_writable(
    tmp_path: Path,
) -> None:
    if shutil.which("bwrap") is None:
        return
    sandbox_home = tmp_path / "home"
    storage_home = tmp_path / "storage-home"
    repo = storage_home / "repo"
    runtime = storage_home / "run"
    secrets = runtime / "secrets"
    sandbox_home.mkdir()
    secrets.mkdir(parents=True)
    repo.mkdir()
    (repo / "marker").write_text("repo-visible\n")
    (repo / ".env").write_text("MODEL_API_KEY=harness-secret\n")
    (repo / ".sandoq-firecracker-token").write_text("exec-secret\n")
    (secrets / "adapter.token").write_text("adapter-secret\n")
    (sandbox_home / "outside.env").write_text("outside-secret\n")
    (storage_home / "outside-storage-token").write_text("storage-secret\n")
    check = "\n".join(
        (
            "set -eu",
            '[ "$(cat "$AAR_REPO/marker")" = repo-visible ]',
            '[ ! -s "$AAR_REPO/.env" ]',
            '[ ! -s "$AAR_REPO/.sandoq-firecracker-token" ]',
            '[ ! -e "$HOME/outside.env" ]',
            '[ ! -e "$VISIBLE_STORAGE_ROOT/outside-storage-token" ]',
            '[ ! -e "/proc/$HOST_PARENT_PID/environ" ]',
            '[ -z "${MODEL_API_KEY+x}" ]',
            '[ -z "$(find "$AAR_RUNTIME_ROOT/secrets" '
            '-mindepth 1 -print -quit)" ]',
            '! touch "$AAR_REPO/repo-write"',
            'touch "$AAR_RUNTIME_ROOT/run-write"',
        )
    )
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(sandbox_home),
        "AAR_REPO": str(repo),
        "AAR_RUNTIME_ROOT": str(runtime),
        "AAR_RESEARCH_ENV_ISOLATION": "1",
        "AAR_RESEARCH_STORAGE_HOME": str(storage_home),
        "VISIBLE_STORAGE_ROOT": str(storage_home),
        "AAR_CLAUDE_REAL_CLI_PATH": "/bin/bash",
        "HOST_PARENT_PID": str(os.getpid()),
        "MODEL_API_KEY": "must-not-reach-sandbox",
    }
    subprocess.run([str(BWRAP), "-c", check], check=True, env=env)
    assert not (repo / "repo-write").exists()
    assert (runtime / "run-write").is_file()
    assert (secrets / "adapter.token").read_text() == "adapter-secret\n"


def test_fileless_research_runtime_does_not_fall_back_to_harness_env(
    tmp_path: Path,
) -> None:
    secret_env = tmp_path / "operator.env"
    secret_env.write_text(
        "MODEL_API_KEY=must-not-load\n"
        "ANTHROPIC_API_KEY=must-not-load\n"
        "AAR_AUTODATA_URL=http://wrong.example\n"
    )
    command = "\n".join(
        (
            "set -euo pipefail",
            f"REPO={str(REPO)!r}",
            "export REPO AAR_RUNTIME_ENV_DISABLE_FILE=1",
            f"export HARNESS_ENV={str(secret_env)!r}",
            "export AAR_AUTODATA_URL=http://adapter.example:8123",
            "export AAR_AUTODATA_TOKEN_FILE=/operator/adapter.token",
            'source "$REPO/scripts/aar_runtime_env.sh"',
            "printf 'harness=%s\\n' \"${HARNESS_ENV-unset}\"",
            "printf 'model=%s\\n' \"${MODEL_API_KEY-unset}\"",
            "printf 'anthropic=%s\\n' \"${ANTHROPIC_API_KEY-unset}\"",
            "printf 'url=%s\\n' \"$AAR_AUTODATA_URL\"",
            "printf 'adapter_file=%s\\n' \"$AAR_AUTODATA_TOKEN_FILE\"",
        )
    )
    completed = subprocess.run(
        ["bash", "-c", command],
        check=True,
        capture_output=True,
        text=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
    )
    assert completed.stdout.splitlines() == [
        "harness=unset",
        "model=unset",
        "anthropic=unset",
        "url=http://adapter.example:8123",
        "adapter_file=/operator/adapter.token",
    ]
