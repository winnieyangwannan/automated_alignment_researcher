"""Regression coverage for one-shot approved-proposal recovery."""

import json
import os
from unittest.mock import patch

from aar.research_loop.kimi_agent import KimiAgent


def test_approved_proposal_recovery_disables_after_finding_persists(
    tmp_path,
) -> None:
    run_id = "chain-candidate-1"
    environment = {
        "AAR_RESUME_APPROVED_PROPOSAL": "1",
        "TEAM_DIR": str(tmp_path),
    }
    with (
        patch.dict(os.environ, environment, clear=False),
        patch.object(KimiAgent, "_approved_run_id", return_value=run_id),
    ):
        assert KimiAgent._resume_approved_proposal_enabled()

        registry = (
            tmp_path / ".finding_dedup" / f"runid_{run_id}" / "post.json"
        )
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({"finding_id": "finding-1"}))

        assert not KimiAgent._resume_approved_proposal_enabled()
