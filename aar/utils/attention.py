"""Conservative attention-backend selection for Hugging Face model loading.

The ``flash-attn-4`` distribution is not, by itself, a Transformers attention
backend.  Transformers must also register ``flash_attention_4`` before it is
safe to pass that name to ``from_pretrained``.  Until then Qwen3.5 uses
PyTorch's supported SDPA path.
"""

from __future__ import annotations

import os
import warnings
from collections.abc import Collection
from importlib import metadata
from typing import Any


_ATTENTION_ENV = "AAR_ATTN_IMPLEMENTATION"
_QWEN35_MARKERS = ("qwen3.5", "qwen3_5", "qwen35")


def _config_identifiers(config: Any | None) -> list[str]:
    """Return architecture identifiers from a (possibly nested) HF config."""
    if config is None:
        return []

    identifiers: list[str] = []
    for attribute in ("model_type", "architectures", "name_or_path", "_name_or_path"):
        value = getattr(config, attribute, None)
        if isinstance(value, (list, tuple)):
            identifiers.extend(str(item) for item in value)
        elif value:
            identifiers.append(str(value))

    # Multimodal Qwen checkpoints put the text architecture in text_config.
    text_config = getattr(config, "text_config", None)
    if text_config is not None and text_config is not config:
        identifiers.extend(_config_identifiers(text_config))
    return identifiers


def is_qwen35(model_ref: str, config: Any | None = None) -> bool:
    """Recognize a Qwen3.5 hub id or a local checkpoint from its HF config."""
    identifiers = [str(model_ref), *_config_identifiers(config)]
    return any(
        marker in identifier.lower()
        for identifier in identifiers
        for marker in _QWEN35_MARKERS
    )


def transformers_attention_backends() -> set[str]:
    """Return attention names registered by the installed Transformers build."""
    try:
        from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
    except (ImportError, AttributeError):
        return set()

    try:
        return set(ALL_ATTENTION_FUNCTIONS.keys())
    except (AttributeError, TypeError):
        return set()


def flash_attention_4_supported(
    *,
    available_backends: Collection[str] | None = None,
    installed_distributions: Collection[str] | None = None,
) -> bool:
    """Check both halves of FA4 support: Transformers adapter and kernels."""
    registered = (
        set(available_backends)
        if available_backends is not None
        else transformers_attention_backends()
    )
    if "flash_attention_4" not in registered:
        return False

    if installed_distributions is not None:
        normalized = {name.lower().replace("_", "-") for name in installed_distributions}
        return "flash-attn-4" in normalized

    try:
        metadata.version("flash-attn-4")
    except metadata.PackageNotFoundError:
        return False
    return True


def select_attention_implementation(
    model_ref: str,
    *,
    config: Any | None = None,
    default: str | None = None,
    available_backends: Collection[str] | None = None,
    installed_distributions: Collection[str] | None = None,
) -> str | None:
    """Select a backend without mistaking an installed kernel for HF support.

    Qwen3.5 uses FlashAttention 4 only when both its distribution and its
    Transformers adapter are present, otherwise it uses ``sdpa``. Other
    architectures keep the caller's existing default (``None`` means let
    Transformers decide). An explicit ``AAR_ATTN_IMPLEMENTATION`` override is
    honored, except that unsupported ``flash_attention_4`` safely falls back.
    """
    qwen35 = is_qwen35(model_ref, config)
    fallback = "sdpa" if qwen35 else default
    fa4_supported = flash_attention_4_supported(
        available_backends=available_backends,
        installed_distributions=installed_distributions,
    )
    requested = os.getenv(_ATTENTION_ENV, "").strip().lower()
    if not requested or requested == "auto":
        if qwen35 and fa4_supported:
            return "flash_attention_4"
        return fallback

    if requested == "flash_attention_4":
        if not fa4_supported:
            warnings.warn(
                "flash_attention_4 requires both the flash-attn-4 distribution "
                "and a Transformers build that registers it; using "
                f"{fallback or 'the Transformers default'} instead",
                RuntimeWarning,
                stacklevel=2,
            )
            return fallback
    return requested
