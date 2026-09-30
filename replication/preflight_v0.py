#!/usr/bin/env python3
"""Non-mutating replication-v0 configuration and Serve API preflight."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.request

from aar.eval_pod.models import split_reasoning_and_answer_text


EXPECTED_BENCHMARKS = ["sycophancy_eval", "sycon_fp", "mmlu", "gsm8k", "ifeval"]


def api_json(url: str, key: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url.rstrip("/") + path,
        data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        raw = response.read()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw.decode(errors="replace")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true", help="also require paid-call keys and measured baseline")
    args = parser.parse_args()

    repo = Path(os.environ["AAR_REPO"]).resolve()
    branch = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--show-current"], text=True
    ).strip()
    if branch != "winnie-replication-v0":
        raise SystemExit(f"wrong branch: {branch!r}")
    if os.environ.get("TARGET_MODEL_PATH") != "/checkpoint/ram/shared/models/google/gemma-4-31B-it":
        raise SystemExit("unexpected TARGET_MODEL_PATH")
    if not Path(os.environ["TARGET_MODEL_PATH"]).is_dir():
        raise SystemExit("Gemma checkpoint is missing")
    actual = os.environ.get("AAR_SUITE_BENCHMARKS", "").replace(",", " ").split()
    if actual != EXPECTED_BENCHMARKS:
        raise SystemExit(f"wrong suite filter: {actual!r}")
    if os.environ.get("AAR_TARGET_ENABLE_THINKING") != "1":
        raise SystemExit("target thinking is not enabled")
    if os.environ.get("AAR_REQUIRE_ADAPTER") != "1":
        raise SystemExit("adapter-only submissions are not enforced")

    deployment = Path(os.environ["AAR_SERVE_V2_DEPLOYMENT_DIR"])
    info = json.loads((deployment / "proxy_info.json").read_text())
    expected_model = os.environ["AAR_SERVE_V2_MODEL"]
    api_json(info["url"], info["api_key"], "/health/readiness")
    models = api_json(info["url"], info["api_key"], "/v1/models")
    advertised = [entry.get("id") for entry in models.get("data", [])]
    if expected_model not in advertised:
        raise SystemExit(f"Serve API model missing: {advertised!r}")
    completion = api_json(info["url"], info["api_key"], "/v1/chat/completions", {
        "model": expected_model,
        "messages": [{"role": "user", "content": "Return exactly the integer result of 17 + 19."}],
        "temperature": 0,
        "max_tokens": 512,
        "chat_template_kwargs": {"enable_thinking": True},
        "skip_special_tokens": False,
    })
    choice = completion["choices"][0]
    reasoning, answer = split_reasoning_and_answer_text(choice["message"]["content"])
    if choice.get("finish_reason") != "stop" or not reasoning or answer.strip() != "36":
        raise SystemExit("thinking completion failed structural checks")

    if args.launch:
        if not Path(os.environ["AAR_BASELINE_OVERRIDES"]).is_file():
            raise SystemExit("measured Gemma baseline override is missing")
        if not (os.getenv("OAI_API") or os.getenv("OPENAI_API_KEY")):
            raise SystemExit("OpenAI judge key is missing")
        if not os.getenv("MODEL_API_KEY"):
            raise SystemExit("Model API key for the Opus monitor is missing")
    print(json.dumps({
        "ok": True,
        "branch": branch,
        "model": "google/gemma-4-31B-it",
        "served_model": expected_model,
        "benchmarks": actual,
        "thinking_reasoning_nonempty": True,
        "thinking_final_answer": answer,
        "launch_gates_checked": args.launch,
    }, indent=2))


if __name__ == "__main__":
    main()
