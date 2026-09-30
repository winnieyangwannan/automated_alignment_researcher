"""Minimal client for a filesystem-discovered Serve API v2 deployment."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.request
from typing import Any

from aar.eval_pod.models import split_reasoning_and_answer_text


def _deployment_info(deployment_dir: str | None = None) -> dict[str, Any]:
    root = Path(deployment_dir or os.environ["AAR_SERVE_V2_DEPLOYMENT_DIR"])
    info = json.loads((root / "proxy_info.json").read_text())
    for key in ("url", "api_key", "model"):
        if not info.get(key):
            raise RuntimeError(f"Serve API deployment metadata is missing {key!r}")
    return info


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    deployment_dir: str | None = None,
    model: str | None = None,
    enable_thinking: bool = True,
    max_tokens: int = 1024,
    temperature: float = 1.0,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Return separated ``answer`` and ``reasoning`` from the deployed target.

    Credentials are read from the deployment metadata only for the HTTP request;
    they are never included in the returned object or exception text.
    """
    info = _deployment_info(deployment_dir)
    served_model = model or os.getenv("AAR_SERVE_V2_MODEL") or info["model"]
    body = {
        "model": served_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
        # Required for deterministic reasoning/final channel separation.
        "skip_special_tokens": False,
    }
    request = urllib.request.Request(
        info["url"].rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {info['api_key']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read())
    choice = payload["choices"][0]
    reasoning, answer = split_reasoning_and_answer_text(choice["message"]["content"])
    if choice.get("finish_reason") != "stop":
        raise RuntimeError(
            f"Serve API completion did not stop cleanly: {choice.get('finish_reason')!r}"
        )
    if enable_thinking and not reasoning:
        raise RuntimeError("Serve API completion omitted the required thought channel")
    if not answer:
        raise RuntimeError("Serve API completion has no final answer")
    return {
        "answer": answer,
        "reasoning": reasoning,
        "model": payload.get("model", served_model),
        "finish_reason": choice["finish_reason"],
        "usage": payload.get("usage", {}),
    }
