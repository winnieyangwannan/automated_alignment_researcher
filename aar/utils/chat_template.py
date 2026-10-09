"""Helpers for normalizing tokenized chat-template output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def normalize_chat_template_ids(value: Any) -> list[int]:
    """Return one token-id sequence from common Transformers return types.

    Depending on the tokenizer and Transformers version, ``apply_chat_template``
    may return a bare list, a one-row nested list, a tensor, or a
    ``BatchEncoding`` containing ``input_ids``. Training methods should not
    silently discard otherwise valid examples merely because the return type
    differs.
    """
    if isinstance(value, Mapping):
        if "input_ids" not in value:
            raise TypeError("tokenized chat template has no input_ids")
        value = value["input_ids"]
    if hasattr(value, "tolist"):
        value = value.tolist()
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 1
        and isinstance(value[0], Sequence)
        and not isinstance(value[0], (str, bytes))
    ):
        value = value[0]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("tokenized chat template is not a token-id sequence")
    result = list(value)
    if any(isinstance(token, bool) or not isinstance(token, int) for token in result):
        raise TypeError("tokenized chat template contains non-integer token IDs")
    return result
