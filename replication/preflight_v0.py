#!/usr/bin/env python3
"""Non-mutating replication-v0 configuration and Serve API preflight."""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import subprocess
import urllib.request

from aar.eval_pod.models import split_reasoning_and_answer_text


EXPECTED_BENCHMARKS = ["sycophancy_eval", "sycon_fp", "mmlu", "gsm8k", "ifeval"]
EXPECTED_JUDGE_BACKEND = "model_api"
EXPECTED_JUDGE_MODEL = "gpt-5-6-luna"
MODEL_API_URL = "https://api.meta.ai"


def require_positive_budget(name: str) -> str:
    value = os.getenv(name, "").strip()
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise SystemExit(f"{name} must be a positive numeric USD authorization cap") from error
    if not amount.is_finite() or amount <= 0:
        raise SystemExit(f"{name} must be a positive numeric USD authorization cap")
    return value


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


def responses_output_text(response: dict) -> str:
    return "".join(
        content.get("text", "")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") == "output_text"
    )


def require_judge_configuration(*, require_key: bool = True) -> str:
    if os.getenv("JUDGE_BACKEND") != EXPECTED_JUDGE_BACKEND:
        raise SystemExit(
            f"JUDGE_BACKEND must be {EXPECTED_JUDGE_BACKEND!r} for replication-v0"
        )
    if os.getenv("JUDGE_MODEL") != EXPECTED_JUDGE_MODEL:
        raise SystemExit(
            f"JUDGE_MODEL must be {EXPECTED_JUDGE_MODEL!r} for replication-v0"
        )
    if os.getenv("OAI_API") or os.getenv("OPENAI_API_KEY"):
        raise SystemExit("public OpenAI credentials must be disabled for replication-v0")
    key = os.getenv("MODEL_API_KEY", "")
    if require_key and not key:
        raise SystemExit("MODEL_API_KEY for the GPT judge is missing")
    return key


def smoke_model_api_judge(api_call=None) -> dict:
    """Make one bounded GPT judge request through the exact production route."""
    key = require_judge_configuration()
    call = api_call or api_json
    response = call(
        MODEL_API_URL,
        key,
        "/v1/responses",
        {
            "model": EXPECTED_JUDGE_MODEL,
            "input": "Return exactly JUDGE_SMOKE_OK and nothing else.",
            "max_output_tokens": 256,
        },
    )
    if response.get("status") != "completed":
        raise SystemExit(
            f"Model API judge smoke did not complete: {response.get('status')!r}"
        )
    if response.get("model") != EXPECTED_JUDGE_MODEL:
        raise SystemExit(
            f"Model API judge smoke returned wrong model: {response.get('model')!r}"
        )
    output = responses_output_text(response).strip()
    if output != "JUDGE_SMOKE_OK":
        raise SystemExit(f"Model API judge smoke returned unexpected output: {output!r}")
    return {
        "endpoint": MODEL_API_URL + "/v1/responses",
        "model": EXPECTED_JUDGE_MODEL,
        "status": response["status"],
        "output": output,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", action="store_true", help="also require paid-call keys and measured baseline")
    parser.add_argument(
        "--canary",
        action="store_true",
        help="require launch gates for the explicitly authorized one-iteration canary",
    )
    parser.add_argument(
        "--baseline-canary",
        action="store_true",
        help="require the judge key for the explicitly authorized canary baseline",
    )
    parser.add_argument(
        "--judge-smoke-only",
        action="store_true",
        help="make one live bounded GPT judge call, then exit",
    )
    parser.add_argument("--require-claude-budget", action="store_true")
    parser.add_argument("--require-gpt-judge-budget", action="store_true")
    args = parser.parse_args()

    repo = Path(os.environ["AAR_REPO"]).resolve()
    branch = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--show-current"], text=True
    ).strip()
    if branch != "uv":
        raise SystemExit(f"wrong branch: {branch!r}")
    if args.judge_smoke_only:
        print(json.dumps({"ok": True, "judge_smoke": smoke_model_api_judge()}, indent=2))
        return
    require_judge_configuration(require_key=False)
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
    if os.environ.get("EVAL_RUN_BATCH") != "2":
        raise SystemExit("replication-v0 EVAL_RUN_BATCH must be 2")
    if os.environ.get("EVAL_AUTO_CEILING") != "8192":
        raise SystemExit("target thinking-plus-answer budget must be 8192")
    if os.environ.get("EVAL_RUN_GEN_CEILING") != "8192":
        raise SystemExit("replication-v0 generation ceiling must be 8192")
    if os.environ.get("MASK_GENERATION_TOKEN_BUDGET") != "8192":
        raise SystemExit("MASK generation budget must be 8192")
    ceiling_benchmarks = os.environ.get(
        "EVAL_RUN_GEN_CEILING_BENCHMARKS", ""
    ).replace(",", " ").split()
    if ceiling_benchmarks != ["sycophancy_eval", "sycon_fp", "gsm8k", "ifeval"]:
        raise SystemExit("replication-v0 generation ceiling scope is incomplete")
    if os.environ.get("EVAL_FAIL_ON_ALLOCATOR_WARNING") != "1":
        raise SystemExit("allocator-warning failure gate is not enabled")
    try:
        truncation_limit = float(os.environ["EVAL_MAX_TRUNCATION_RATE"])
        truncation_minimum = int(os.environ["EVAL_TRUNCATION_MIN_COMPLETIONS"])
    except (KeyError, ValueError) as error:
        raise SystemExit("invalid truncation-health configuration") from error
    if not 0 <= truncation_limit < 1 or truncation_minimum <= 0:
        raise SystemExit("invalid truncation-health limits")

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

    claude_budget = None
    gpt_judge_budget = None
    if args.launch or args.require_claude_budget:
        claude_budget = require_positive_budget("AAR_CLAUDE_SPEND_CAP_USD")
    if args.launch or args.require_gpt_judge_budget:
        gpt_judge_budget = require_positive_budget("AAR_GPT_JUDGE_SPEND_CAP_USD")
    if args.launch or args.require_gpt_judge_budget or args.baseline_canary or args.canary:
        require_judge_configuration()

    if args.launch or args.canary:
        for marker in ("environment.ok", "gpu.ok", "evaluator_gpu.ok", "web.ok"):
            path = Path(os.environ["AAR_RUNTIME_ROOT"]) / "preflight" / marker
            if not path.is_file():
                raise SystemExit(f"required preflight marker is missing: {path}")
        if not Path(os.environ["AAR_BASELINE_OVERRIDES"]).is_file():
            raise SystemExit("measured Gemma baseline override is missing")
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
        "judge_backend": os.environ.get("JUDGE_BACKEND"),
        "judge_model": os.environ.get("JUDGE_MODEL"),
        "evaluation_batch_size": int(os.environ["EVAL_RUN_BATCH"]),
        "freeform_generation_ceiling": int(
            os.environ["EVAL_RUN_GEN_CEILING"]
        ),
        "generation_ceiling_benchmarks": ceiling_benchmarks,
        "max_truncation_rate": truncation_limit,
        "launch_gates_checked": args.launch,
        "one_iteration_canary_gates_checked": args.canary,
        "claude_spend_cap_usd": claude_budget,
        "gpt_judge_spend_cap_usd": gpt_judge_budget,
    }, indent=2))


if __name__ == "__main__":
    main()
