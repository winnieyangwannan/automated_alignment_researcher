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
