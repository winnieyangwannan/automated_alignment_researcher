from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BWRAP = ROOT / "scripts" / "claude_research_bwrap.sh"
RUNTIME_ENV = ROOT / "scripts" / "aar_runtime_env.sh"
CHAIN = ROOT / "scripts" / "slurm_aar_chain.sh"


def test_shell_syntax() -> None:
    for path in (BWRAP, RUNTIME_ENV, CHAIN):
        subprocess.run(["bash", "-n", str(path)], check=True)


def test_sandbox_mounts_only_configured_plugin_read_only() -> None:
    source = BWRAP.read_text()
    assert 'autodata_plugin_root="${AAR_AUTODATA_PLUGIN_ROOT:-}"' in source
    assert 'bind_visible_dir "${autodata_plugin_root}" ro' in source
    assert '--setenv AAR_AUTODATA_PLUGIN_ROOT "${autodata_plugin_root}"' in source
    assert '--setenv AUTODATA_CACHE_DIR "${runtime_root}/autodata/plugin-cache"' in source
    assert 'bind_visible_dir "${storage_home}"' not in source


def test_sandbox_exposes_only_node_local_autodata_state_at_run_alias() -> None:
    source = BWRAP.read_text()
    assert 'autodata_state="${AAR_AUTODATA_STATE:-}"' in source
    assert 'autodata_state_visible="${runtime_root}/autodata/live-state"' in source
    assert '--bind "${autodata_state_root}" "${autodata_state_visible}"' in source
    assert '--setenv AAR_AUTODATA_STATE "${autodata_state_visible}/$(basename' in source


def test_sandbox_exposes_attempt_local_method_validation_tools() -> None:
    source = BWRAP.read_text()
    submitter = (ROOT / "scripts" / "submit_train_job.sh").read_text()

    assert 'research_tool_dir="${AAR_RESEARCH_TOOL_DIR:-}"' in source
    assert '"${runtime_root}"/*)' in source
    assert '--setenv AAR_METHOD_VALIDATOR_PY /usr/bin/python3' in source
    assert '--setenv PATH "${research_tool_dir}:${PATH}"' in source
    assert 'AAR_METHOD_VALIDATOR_PY:-${HARNESS_PY:-python}' in submitter


def test_sandbox_exposes_only_trusted_external_python_environment() -> None:
    source = BWRAP.read_text()

    assert 'trusted_harness_py="${AAR_TRUSTED_HARNESS_PY:-${HARNESS_PY:-}}"' in source
    assert '[ -x "${trusted_harness_py}" ]' in source
    assert '[ -f "${trusted_harness_root}/pyvenv.cfg" ]' in source
    assert 'bind_visible_dir "${trusted_harness_root}" ro' in source
    assert 'trusted_harness_real="$(realpath -e -- "${trusted_harness_py}")"' in source
    assert 'bind_visible_dir "${trusted_harness_base_root}" ro' in source
    assert 'bind_visible_dir "${storage_home}"' not in source


def test_sandbox_can_bind_relocated_run_artifacts_read_write() -> None:
    source = BWRAP.read_text()
    runtime = RUNTIME_ENV.read_text()

    assert 'artifact_root="${AAR_RUNTIME_ARTIFACT_ROOT:-}"' in source
    assert '[ -n "${root}" ] || return 0' in source
    assert 'bind_visible_dir "${artifact_root}" rw' in source
    assert '"${artifact_root:+${artifact_root}/eval/holdout}"' in source
    assert 'artifact_team_eval_private="${resolved_team_dir}/_eval_private"' in source
    assert "AAR_RUNTIME_ARTIFACT_ROOT" in runtime


def test_sandbox_masks_team_secret_directory_after_rw_bind() -> None:
    source = BWRAP.read_text()

    assert 'resolved_team_dir="$(realpath -e -- "${TEAM_DIR}")"' in source
    assert 'team_secret_root="${resolved_team_dir}/secrets"' in source
    assert '"${team_secret_root}"' in source
    assert 'bwrap_args+=(--tmpfs "${secret_root}")' in source


def test_runtime_exports_plugin_inputs_not_adapter_configuration() -> None:
    runtime = RUNTIME_ENV.read_text()
    chain = CHAIN.read_text()
    combined = runtime + chain

    assert "AAR_AUTODATA_PLUGIN_ROOT" in runtime
    assert "AAR_AUTODATA_SHA" in runtime
    assert "AAR_AUTODATA_URL" not in combined
    assert "AAR_AUTODATA_TOKEN" not in combined
    assert "AAR_AUTODATA_CONTRACT_SMOKE" not in combined
    assert "autodata_contract_smoke_server.py" not in combined
