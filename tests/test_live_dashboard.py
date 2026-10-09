from aar.web_ui.live_dashboard import _chain_of


def test_chain_of_supports_arbitrary_parallel_chain_names():
    assert _chain_of({"idea_name": "gemma4_31b-explore-delta"}) == "delta"
    assert _chain_of({"idea_name": "gemma4_31b-explore-epsilon"}) == "epsilon"


def test_chain_of_falls_back_to_timestamped_idea_uid():
    finding = {"idea_uid": "gemma4_31b-explore-zeta-1791334145"}

    assert _chain_of(finding) == "zeta"


def test_chain_of_uses_team_for_unrecognized_findings():
    assert _chain_of({"idea_name": "legacy-method"}) == "team"
