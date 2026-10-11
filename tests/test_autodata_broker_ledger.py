from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.autodata_broker_ledger import restore, snapshot


def _ledger(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE jobs (
              idempotency_key TEXT PRIMARY KEY,
              job_id TEXT NOT NULL,
              status TEXT NOT NULL
            );
            CREATE TABLE campaign_usage (
              campaign_id TEXT PRIMARY KEY,
              spent_usd TEXT NOT NULL,
              reserved_usd TEXT NOT NULL,
              cap_usd TEXT NOT NULL
            );
            INSERT INTO jobs VALUES ('semantic-key', 'job-one', 'running');
            INSERT INTO campaign_usage VALUES ('campaign', '12.5', '8.25', '6000');
            """
        )


def test_restart_preserves_idempotent_job_and_campaign_totals(tmp_path: Path) -> None:
    live = tmp_path / "session-one" / "broker.db"
    live.parent.mkdir()
    retained = tmp_path / "retained" / "campaign-ledger.db"
    _ledger(live)

    assert snapshot(live, retained) is True
    restored = tmp_path / "session-two" / "broker.db"
    assert restore(retained, restored) is True

    with sqlite3.connect(restored) as connection:
        assert connection.execute(
            "SELECT job_id,status FROM jobs WHERE idempotency_key='semantic-key'"
        ).fetchone() == ("job-one", "running")
        assert connection.execute(
            "SELECT spent_usd,reserved_usd,cap_usd FROM campaign_usage"
        ).fetchone() == ("12.5", "8.25", "6000")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO jobs VALUES ('semantic-key','job-duplicate','queued')"
            )


def test_restore_rejects_tampered_campaign_ledger(tmp_path: Path) -> None:
    live = tmp_path / "live.db"
    retained = tmp_path / "retained.db"
    _ledger(live)
    snapshot(live, retained)
    manifest = retained.with_name("retained.db.snapshot.json")
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text.replace('"sha256": "', '"sha256": "0'), encoding="utf-8")

    with pytest.raises(RuntimeError, match="digest"):
        restore(retained, tmp_path / "restored.db")
