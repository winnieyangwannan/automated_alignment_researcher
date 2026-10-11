from __future__ import annotations

from pathlib import Path

from aar.research_loop import monitor


def test_monitor_failure_is_static_and_raw_detail_is_masked(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEAM_DIR", str(tmp_path))
    monkeypatch.setenv("AAR_MONITOR_BACKEND", "bad-backend-API_KEY=secret")

    result = monitor._call_monitor("private proposed method")

    assert result["approved"] is False
    assert result["reasoning"] == "integrity monitor unavailable (fail-closed)"
    assert "bad-backend" not in str(result)
    failure = result["failure"]
    assert failure["error_code"] == "integrity_monitor_failed"
    assert failure["retryable"] is True
    assert "evidence" not in failure
    assert not (tmp_path / "secrets").exists()


def test_self_containment_failure_does_not_return_transport_body(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TEAM_DIR", str(tmp_path))
    monkeypatch.setattr(monitor, "_monitor_api_key", lambda: "configured")

    def fail(*_args, **_kwargs):
        raise RuntimeError("HTTP body heldout-row-44 token=secret")

    monkeypatch.setattr(monitor, "_post_retry", fail)

    result = monitor.check_self_containment("method paper " * 10)

    assert result["clean"] is True
    assert result["reasoning"] == (
        "self-containment classifier unavailable (fail-open)"
    )
    assert "heldout-row-44" not in str(result)
    assert result["failure"]["error_code"] == "self_containment_monitor_failed"
