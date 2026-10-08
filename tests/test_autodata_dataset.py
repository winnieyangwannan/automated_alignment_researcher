from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from aar.infrastructure.autodata_dataset import load_autodata_dataset


def _dataset(*, accepted: bool = True, mode: str = "production") -> dict:
    usage = [
        {
            "request_id": "kimi-1",
            "role": "generator",
            "model": "Kimi-K2.6",
            "input_tokens": 10,
            "output_tokens": 20,
            "estimated_cost_usd": "0.00009",
        },
        {
            "request_id": "luna-1",
            "role": "judge",
            "model": "gpt-5-6-luna",
            "input_tokens": 30,
            "output_tokens": 4,
            "estimated_cost_usd": "0.000046",
        },
    ]
    return {
        "schema": "autodata.dataset/v1",
        "execution_id": "exec_test",
        "mode": mode,
        "items": [
            {
                "id": "row-1",
                "prompt": "Question",
                "response": "Answer",
                "metadata": {"judge_accepted": accepted},
                "_autodata_usage": usage,
            }
        ],
    }


def test_load_records_bound_consumption_receipt():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.json"
        dataset.write_text(json.dumps(_dataset(), sort_keys=True))
        receipt = root / "receipt.json"
        rows = load_autodata_dataset(
            dataset,
            receipt_path=receipt,
            required_rows=1,
            expected_execution_id="exec_test",
        )
        assert len(rows) == 1
        saved = json.loads(receipt.read_text())
        assert saved["row_count"] == 1
        assert saved["model_calls"] == 2


@pytest.mark.parametrize(
    "value,error",
    [
        (_dataset(accepted=False), "judge-rejected"),
        (_dataset(mode="meta_optimize"), "production execution"),
    ],
)
def test_load_fails_closed(value: dict, error: str):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        dataset = root / "dataset.json"
        dataset.write_text(json.dumps(value))
        with pytest.raises(ValueError, match=error):
            load_autodata_dataset(
                dataset,
                receipt_path=root / "receipt.json",
                required_rows=1,
                expected_execution_id="exec_test",
            )
