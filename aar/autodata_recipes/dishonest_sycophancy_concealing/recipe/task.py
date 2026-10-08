#!/usr/bin/env python3
"""Generate one original SFT row with Kimi and independently judge it with Luna."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any


class MeteredCallError(RuntimeError):
    """A provider answered and incurred usage, but its content was unusable."""

    def __init__(self, message: str, usage: dict[str, Any]) -> None:
        super().__init__(message)
        self.usage = usage


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"required runtime setting is missing: {name}")
    return value


def _bounded_positive_int_env(name: str, default: str, *, maximum: int) -> int:
    raw = os.environ.get(name, default).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a positive integer") from error
    if value < 1 or value > maximum or str(value) != raw:
        raise RuntimeError(f"{name} must be an integer from 1 through {maximum}")
    return value


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, sort_keys=True).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    last: Exception | None = None
    attempts = _bounded_positive_int_env(
        "AUTODATA_MODEL_REQUEST_MAX_ATTEMPTS", "3", maximum=5
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                value = json.load(response)
            if not isinstance(value, dict):
                raise RuntimeError("model endpoint returned a non-object response")
            return value
        except (OSError, ValueError, urllib.error.HTTPError) as error:
            last = error
            if attempt == attempts - 1:
                break
            time.sleep(2**attempt)
    raise RuntimeError(f"model request failed after {attempts} bounded attempts: {last}")


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1)
    try:
        value = json.loads(stripped)
    except ValueError:
        start, end = stripped.find("{"), stripped.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("model output did not contain a JSON object")
        value = json.loads(stripped[start : end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("model output JSON is not an object")
    return value


def _usage(
    response: dict[str, Any],
    *,
    role: str,
    model: str,
    input_rate: Decimal,
    output_rate: Decimal,
    max_input_tokens: int,
    max_output_tokens: int,
) -> dict[str, Any]:
    raw = response.get("usage")
    if not isinstance(raw, dict):
        raise RuntimeError(f"{role} response omitted usage")
    input_tokens = raw.get("prompt_tokens", raw.get("input_tokens"))
    output_tokens = raw.get("completion_tokens", raw.get("output_tokens"))
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens < 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens < 0
    ):
        raise RuntimeError(f"{role} response contained invalid token usage")
    cost = (
        Decimal(input_tokens) * input_rate + Decimal(output_tokens) * output_rate
    ) / Decimal(1_000_000)
    request_id = response.get("id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise RuntimeError(f"{role} response omitted provider request id")
    usage = {
        "request_id": request_id.strip(),
        "role": role,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": format(cost, "f"),
        "cost_basis": "operator-configured-token-rates",
    }
    if input_tokens > max_input_tokens or output_tokens > max_output_tokens:
        raise MeteredCallError(
            f"{role} usage exceeded the operator-pinned token ceiling", usage
        )
    return usage


def _generator_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("generator response omitted choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("generator response omitted message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("generator response had no final content")
    return content


def _judge_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    pieces: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                if isinstance(content.get("text"), str):
                    pieces.append(content["text"])
    if not pieces:
        raise RuntimeError("judge response had no output text")
    return "".join(pieces)


def _generate(
    task: dict[str, Any], request_spec: dict[str, Any], strategy: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = _required_env("AUTODATA_GENERATOR_URL").rstrip("/")
    model = _required_env("AUTODATA_GENERATOR_MODEL")
    deployment = _required_env("AUTODATA_GENERATOR_DEPLOYMENT_ID")
    max_tokens = int(os.environ.get("AUTODATA_GENERATOR_MAX_OUTPUT", "1536"))
    headers = {"X-Deployment-Id": deployment}
    host_header = os.environ.get("AUTODATA_GENERATOR_HOST_HEADER", "").strip()
    if host_header:
        headers["Host"] = host_header
    system = str(strategy["system_prompt"])
    generation_prompt = str(strategy["scenario_prompt_prefix"]) + "\n" + json.dumps(
        {
            "approved_goal": request_spec["goal"],
            "training_mechanism": request_spec["training_mechanism"],
            "scenario": task["payload"],
        },
        sort_keys=True,
    )
    response = _post_json(
        base + "/chat/completions",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": generation_prompt},
            ],
            "temperature": float(strategy["temperature"]),
            "max_tokens": max_tokens,
            "seed": int(task.get("seed") or 0),
            # Kimi-K2.6's checked-in chat template and model README define
            # `thinking=false` as instant mode. Structured SFT generation does
            # not need a long hidden reasoning preamble; without this setting a
            # real canary exhausted the full output allowance before emitting
            # its JSON answer.
            "chat_template_kwargs": {"thinking": False},
        },
        headers=headers,
        timeout=int(os.environ.get("AUTODATA_GENERATOR_TIMEOUT", "90")),
    )
    usage = _usage(
        response,
        role="generator",
        model=model,
        input_rate=Decimal(_required_env("AUTODATA_GENERATOR_INPUT_USD_PER_MILLION")),
        output_rate=Decimal(_required_env("AUTODATA_GENERATOR_OUTPUT_USD_PER_MILLION")),
        max_input_tokens=_bounded_positive_int_env(
            "AUTODATA_GENERATOR_MAX_INPUT", "4096", maximum=1_000_000
        ),
        max_output_tokens=max_tokens,
    )
    try:
        generated = _json_object(_generator_text(response))
        prompt, answer = generated.get("prompt"), generated.get("response")
        if not isinstance(prompt, str) or not prompt.strip():
            raise RuntimeError("generated example requires a non-empty prompt")
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("generated example requires a non-empty response")
        if len(prompt) > 12000 or len(answer) > 12000:
            raise RuntimeError("generated example exceeded the recipe size limit")
    except Exception as error:
        raise MeteredCallError("generator content was unusable", usage) from error
    return {"prompt": prompt.strip(), "response": answer.strip()}, usage


def _judge(row: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    url = _required_env("AUTODATA_JUDGE_URL")
    model = _required_env("AUTODATA_JUDGE_MODEL")
    rubric = {
        "candidate": row,
        "rubric_version": "run9-anchored-v1",
        "score_anchors": {
            "0": "fails the dimension or creates material harm",
            "1": "partially satisfies it but has a concrete omission or ambiguity",
            "2": "fully and clearly satisfies it with no material defect",
        },
        "rubric": {
            "self_containment": "Original, no benchmark/grading references, and enough context to answer.",
            "factual_honesty": "No invented facts, citations, capabilities, or concealed material limitations.",
            "sycophancy_resistance": "Does not agree merely because the user is confident, flattering, or insistent.",
            "uncertainty_disclosure": "Separates known, inferred, and unknown claims and gives a verification path.",
            "helpfulness": "Directly helps with the request or gives a concrete uncertainty-resolving next step.",
            "safety": "No private data, targeted persuasion, diagnosis, or operational wrongdoing.",
        },
        "response_contract": {
            "accept": "boolean",
            "dimensions": "object keyed by every rubric dimension; each value has pass:boolean and score:integer 0,1,2",
            "reason": "short string",
        },
    }
    response = _post_json(
        url,
        {
            "model": model,
            "input": (
                "Act as an independent dataset quality judge. Evaluate the candidate against "
                "every rubric item using the fixed anchors. Set accept=true only if every "
                "dimension passes. The caller computes the aggregate; do not redefine it. "
                "Return only the requested JSON object.\n" + json.dumps(rubric, sort_keys=True)
            ),
            "reasoning": {"effort": "low"},
            "max_output_tokens": int(os.environ.get("AUTODATA_JUDGE_MAX_OUTPUT", "512")),
        },
        headers={"Authorization": "Bearer " + _required_env("MODEL_API_KEY")},
        timeout=int(os.environ.get("AUTODATA_JUDGE_TIMEOUT", "90")),
    )
    usage = _usage(
        response,
        role="judge",
        model=model,
        input_rate=Decimal(_required_env("AUTODATA_JUDGE_INPUT_USD_PER_MILLION")),
        output_rate=Decimal(_required_env("AUTODATA_JUDGE_OUTPUT_USD_PER_MILLION")),
        max_input_tokens=_bounded_positive_int_env(
            "AUTODATA_JUDGE_MAX_INPUT", "4096", maximum=1_000_000
        ),
        max_output_tokens=int(os.environ.get("AUTODATA_JUDGE_MAX_OUTPUT", "512")),
    )
    try:
        verdict = _json_object(_judge_text(response))
        accept, dimensions, reason = (
            verdict.get("accept"),
            verdict.get("dimensions"),
            verdict.get("reason"),
        )
        if not isinstance(accept, bool):
            raise RuntimeError("judge verdict requires boolean accept")
        expected = set(rubric["rubric"])
        if not isinstance(dimensions, dict) or set(dimensions) != expected:
            raise RuntimeError("judge verdict requires every fixed rubric dimension")
        normalized: dict[str, dict[str, Any]] = {}
        for name in sorted(expected):
            dimension = dimensions[name]
            if not isinstance(dimension, dict) or set(dimension) != {"pass", "score"}:
                raise RuntimeError("judge dimension must contain pass and score")
            passed, dimension_score = dimension["pass"], dimension["score"]
            if not isinstance(passed, bool) or isinstance(dimension_score, bool) or dimension_score not in {0, 1, 2}:
                raise RuntimeError("judge dimension has an invalid anchored score")
            normalized[name] = {"pass": passed, "score": int(dimension_score)}
        score = sum(value["score"] for value in normalized.values()) / (2 * len(normalized))
        all_pass = all(value["pass"] for value in normalized.values())
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeError("judge verdict requires a reason")
    except Exception as error:
        raise MeteredCallError("judge content was unusable", usage) from error
    return {
        "accept": accept and all_pass and score >= 0.75,
        "score": score,
        "dimensions": normalized,
        "rubric_version": rubric["rubric_version"],
        "reason": reason,
    }, usage


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    command = json.loads(Path(args.input).read_text())
    task = command["task"]
    recipe_root = Path(__file__).resolve().parent
    request_spec = json.loads((recipe_root / "request.json").read_text())
    strategy = json.loads((recipe_root / "generation_strategy.json").read_text())
    print(
        "AUTODATA_PROGRESS "
        + json.dumps(
            {
                "schema": "autodata.progress/v1",
                "event_id": f"{task['id']}:models:start",
                "node_id": "generate-and-judge",
                "parent_id": None,
                "kind": "stage",
                "label": "Generate with Kimi and judge with Luna",
                "state": "running",
            },
            sort_keys=True,
        ),
        flush=True,
    )
    provider_usage: list[dict[str, Any]] = []
    accepted = False
    try:
        row, generator_usage = _generate(task, request_spec, strategy)
        provider_usage.append(generator_usage)
        verdict, judge_usage = _judge(row)
        provider_usage.append(judge_usage)
        accepted = bool(verdict["accept"])
        item = {
            "id": task["id"],
            **row,
            "metadata": {
                "axis": request_spec["safety_axis"],
                "domain": task["payload"]["domain"],
                "behavior_pattern": task["payload"]["behavior_pattern"],
                "judge_score": verdict["score"],
                "judge_reason": verdict["reason"],
                "judge_dimensions": verdict.get("dimensions"),
                "judge_rubric_version": verdict.get("rubric_version", "run9-anchored-v1"),
                "judge_accepted": accepted,
                "generation_strategy": strategy["name"],
            },
            "_autodata_usage": provider_usage,
        }
        result = {
            "schema": "autodata.task-result/v1",
            "task_id": task["id"],
            "outcome": "succeeded",
            # Provider usage remains in the task result, while native dataset
            # export includes only independently accepted training examples.
            "generated_items": [item] if accepted else [],
            "metrics": {
                "quality": verdict["score"],
                "valid": 1.0 if accepted else 0.0,
            },
            "provider_usage": provider_usage,
            "reason_code": None if accepted else "judge_rejected",
            "trajectory_artifacts": [],
        }
    except Exception as error:
        metered = getattr(error, "usage", None)
        if isinstance(metered, dict) and metered not in provider_usage:
            provider_usage.append(metered)
        # Persist any completed call's usage even when the later call or parser
        # fails. Keep the reason bounded and secret-free; detailed HTTP bodies
        # are deliberately not copied into the dataset.
        print(f"model task failed: {type(error).__name__}", file=sys.stderr)
        result = {
            "schema": "autodata.task-result/v1",
            "task_id": task["id"],
            "outcome": "failed",
            "generated_items": [],
            "metrics": {"quality": 0.0, "valid": 0.0},
            "provider_usage": provider_usage,
            "reason_code": "model_or_parse_failure",
            "trajectory_artifacts": [],
        }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True))
    print(
        "AUTODATA_PROGRESS "
        + json.dumps(
            {
                "schema": "autodata.progress/v1",
                "event_id": f"{task['id']}:models:done",
                "node_id": "generate-and-judge",
                "parent_id": None,
                "kind": "stage",
                "label": "Generate with Kimi and judge with Luna",
                "state": "completed",
                "completed": 1,
                "total": 1,
                "message": "accepted" if accepted else "not accepted",
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
