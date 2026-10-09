from __future__ import annotations

import pytest

from aar.utils.chat_template import normalize_chat_template_ids


class _TensorLike:
    def tolist(self) -> list[list[int]]:
        return [[7, 8, 9]]


def test_normalizes_plain_nested_and_mapping_outputs() -> None:
    assert normalize_chat_template_ids([1, 2, 3]) == [1, 2, 3]
    assert normalize_chat_template_ids([[4, 5, 6]]) == [4, 5, 6]
    assert normalize_chat_template_ids({"input_ids": [7, 8, 9]}) == [7, 8, 9]
    assert normalize_chat_template_ids({"input_ids": _TensorLike()}) == [7, 8, 9]


@pytest.mark.parametrize(
    "value",
    [
        {},
        "1 2 3",
        [1, True, 3],
        [[1], [2]],
    ],
)
def test_rejects_malformed_outputs(value: object) -> None:
    with pytest.raises(TypeError):
        normalize_chat_template_ids(value)
