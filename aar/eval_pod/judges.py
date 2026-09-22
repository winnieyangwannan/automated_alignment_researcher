"""Judge backends for JudgeBenchmark.

A judge is a `Callable[[str], Optional[bool]]`: it receives the benchmark's
rendered judge prompt and returns the verdict — `True` (correct/acceptable),
`False` (incorrect), or **`None` = SKIP**. None means the judge could NOT reach a
verdict (e.g. the OpenAI API kept erroring), so the item must be EXCLUDED from the
metric entirely — counted neither correct nor incorrect.

BOARD-WIDE RULE (do not regress): a judge error MUST NEVER be defaulted to an
answer. The old behaviour ("fail-closed -> False") silently scored every item the
judge couldn't grade as INCORRECT, so a transient OpenAI 5xx/429 burst depressed
real scores (and fed wrong signal to the hill-climb). Instead: retry the API a few
times with backoff, and if it still won't answer, return None (skip). Every scorer
drops None before aggregating, so the metric is computed only over items that were
actually judged. See aar/benchmarks/base.py:score_from_verdicts.

Backends:
- OpenAI (gpt-4o over httpx) — retries transient errors, then skips.
- FAIR Model API (Responses API over httpx) — selected by MODEL_API_KEY when no
  public OpenAI key is configured; retries transient errors, then skips.
- LOCAL (on-GPU HF instruct model, default Qwen2.5-7B-Instruct) — on error, skips.

A judge is a `Callable[[str], Optional[bool]]`.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_OAI_URL = "https://api.openai.com/v1/chat/completions"
_MODEL_API_URL = "https://api.meta.ai/v1/responses"
_VERDICT_SUFFIX = "\n\nRespond with ONLY 'YES' (correct) or 'NO' (incorrect)."

# Retry budget for API judges: up to this many RETRIES after the first try (so
# 1 + _JUDGE_RETRIES total attempts) with exponential backoff, then SKIP (None).
_JUDGE_RETRIES = 5


def make_local_judge(model: str | None = None) -> Callable[[str], bool]:
    """Return a judge_fn backed by a LOCAL HF instruct model (no API).

    The model is loaded lazily on first call and shared across calls; a lock
    serializes generation so the benchmark's ThreadPoolExecutor judge phase is
    safe on a single GPU. Short greedy decode + the same YES/NO parse + fail-closed
    semantics as the OpenAI judge, so it's a drop-in replacement.

    NOTE: serialized (GPU-bound). For very large judge sets, a batched judge
    interface would be faster — TODO if it becomes the bottleneck.
    """
    model_id = model or os.getenv("JUDGE_MODEL_LOCAL", "Qwen/Qwen2.5-7B-Instruct")
    holder: dict[str, object] = {}
    lock = threading.Lock()

    def _model():
        if "m" not in holder:
            from aar.eval_pod.models import HFModel
            logger.info("loading local judge model: %s", model_id)
            holder["m"] = HFModel(model_id, max_new_tokens=8)
        return holder["m"]

    def judge(judge_prompt: str) -> Optional[bool]:
        try:
            with lock:
                out = _model().generate(judge_prompt + _VERDICT_SUFFIX, max_new_tokens=8)
            return out.strip().upper().startswith("YES")
        except Exception as e:  # NEVER default to an answer -> SKIP (excluded from the metric)
            logger.warning("local judge error (-> SKIP, item excluded from metric): %s", e)
            return None

    return judge


def _model_api_name(model: str) -> str:
    """Normalize friendly model spellings to Model API catalog identifiers."""
    return {"gpt-5.6-luna": "gpt-5-6-luna"}.get(model, model)


def _responses_output_text(response: dict) -> str:
    """Extract assistant text from an OpenAI Responses-shaped response."""
    return "".join(
        content.get("text", "")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") == "output_text"
    )


def make_openai_judge(
    api_key: str | None = None, model: str = "gpt-4o"
) -> Callable[[str], Optional[bool]]:
    """Return a judge backed by public OpenAI or FAIR's Model API.

    An explicit ``api_key`` or OAI_API/OPENAI_API_KEY keeps the existing public
    OpenAI Chat Completions path. When those are absent, MODEL_API_KEY selects
    FAIR's Responses endpoint. Both routes retry transient errors and return
    None (SKIP) after a terminal failure.
    """
    import httpx

    openai_key = api_key or os.getenv("OAI_API") or os.getenv("OPENAI_API_KEY")
    model_api_key = os.getenv("MODEL_API_KEY")
    key = openai_key or model_api_key
    if not key:
        raise RuntimeError(
            "No judge API key (set OAI_API / OPENAI_API_KEY or MODEL_API_KEY)."
        )

    use_model_api = not openai_key and bool(model_api_key)
    endpoint = _MODEL_API_URL if use_model_api else _OAI_URL
    request_model = _model_api_name(model) if use_model_api else model

    client = httpx.Client(timeout=30.0)

    def judge(judge_prompt: str) -> Optional[bool]:
        prompt = judge_prompt + _VERDICT_SUFFIX
        last_err = None
        for attempt in range(_JUDGE_RETRIES + 1):   # 1 initial try + up to _JUDGE_RETRIES retries
            try:
                if use_model_api:
                    payload = {
                        "model": request_model,
                        "input": prompt,
                        # Reasoning models may spend part of this budget before
                        # emitting the short YES/NO answer.
                        "max_output_tokens": 256,
                    }
                else:
                    payload = {
                        "model": request_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": 4,
                    }
                r = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
                r.raise_for_status()
                if use_model_api:
                    output = _responses_output_text(r.json())
                    if not output:
                        raise ValueError("Model API response contained no output text")
                else:
                    output = r.json()["choices"][0]["message"]["content"]
                return output.strip().upper().startswith("YES")
            except httpx.HTTPStatusError as e:
                last_err = e
                code = e.response.status_code
                # Only 429 + 5xx are transient/worth retrying; other 4xx (e.g. 400/401)
                # won't change on retry -> stop and SKIP immediately.
                if code != 429 and code < 500:
                    break
            except Exception as e:  # network / timeout / decode — transient, retry
                last_err = e
            if attempt < _JUDGE_RETRIES:
                time.sleep(min(2 ** attempt, 30))    # backoff 1,2,4,8,16s
        logger.warning("judge error after %d attempt(s) (-> SKIP, item excluded from metric): %s",
                       _JUDGE_RETRIES + 1, last_err)
        return None

    return judge


def make_model_api_judge(
    model: str = "claude-4-8-opus",
) -> Callable[[str], Optional[bool]]:
    """Return a YES/NO judge backed explicitly by FAIR's Responses API."""
    from aar.benchmarks._judge_http import _model_api_key, model_api_chat

    if not _model_api_key():
        raise RuntimeError("No FAIR Model API key (set MODEL_API_KEY).")

    def judge(judge_prompt: str) -> Optional[bool]:
        try:
            output = model_api_chat(
                [{"role": "user", "content": judge_prompt + _VERDICT_SUFFIX}],
                model=model,
                max_tokens=256,
            )
            return output.strip().upper().startswith("YES")
        except Exception as error:  # NEVER turn an API error into a verdict
            logger.warning("Model API judge error (-> SKIP): %s", error)
            return None

    return judge


def make_anthropic_judge(api_key: str | None = None,
                         model: str = "claude-haiku-4-5") -> Callable[[str], Optional[bool]]:
    """Return a YES/NO judge_fn backed by Anthropic (default claude-haiku-4-5) — a drop-in
    for make_openai_judge (cheaper, no OpenAI). Same SKIP-on-error contract: retries transient
    errors via anthropic_chat, and if it still can't get a verdict returns None = SKIP (item
    EXCLUDED from the metric, NEVER defaulted). Requires ANTHROPIC_API_KEY / ANT_high_prio_API /
    ANT_API_KEY."""
    from aar.benchmarks._judge_http import anthropic_chat, _anthropic_key
    if not (api_key or _anthropic_key()):
        raise RuntimeError("No Anthropic API key (set ANTHROPIC_API_KEY / ANT_high_prio_API / "
                           "ANT_API_KEY) for the judge.")

    def judge(judge_prompt: str) -> Optional[bool]:
        prompt = judge_prompt + _VERDICT_SUFFIX
        try:
            # anthropic_chat already retries 429/5xx/529 with backoff; a terminal failure raises.
            out = anthropic_chat([{"role": "user", "content": prompt}], model=model, max_tokens=4)
            return out.strip().upper().startswith("YES")
        except Exception as e:  # NEVER default to an answer -> SKIP (excluded from the metric)
            logger.warning("anthropic judge error (-> SKIP, item excluded from metric): %s", e)
            return None

    return judge


def make_local_judge_batch(model: str | None = None):
    """BATCHED local judge: takes a LIST of judge prompts, returns a list of bools in one
    batched generation (the GPU throughput win) instead of one serialized call per prompt.
    Used by judge benchmarks with many judge calls (truthfulqa_gen: 2x817) to stay inside the
    per-iteration time budget. Same YES/NO parse + fail-closed (any error -> all False)."""
    model_id = model or os.getenv("JUDGE_MODEL_LOCAL", "Qwen/Qwen2.5-7B-Instruct")
    holder: dict[str, object] = {}
    lock = threading.Lock()

    def _model():
        if "m" not in holder:
            from aar.eval_pod.models import HFModel
            logger.info("loading local batch-judge model: %s", model_id)
            holder["m"] = HFModel(model_id, max_new_tokens=8)
        return holder["m"]

    def judge_batch(prompts: list[str]) -> list[Optional[bool]]:
        if not prompts:
            return []
        try:
            with lock:
                outs = _model().generate_batch([p + _VERDICT_SUFFIX for p in prompts], max_new_tokens=8)
            return [o.strip().upper().startswith("YES") for o in outs]
        except Exception as e:  # NEVER default to an answer -> SKIP all (excluded from the metric)
            logger.warning("local batch-judge error (-> SKIP %d items, excluded from metric): %s",
                           len(prompts), e)
            return [None] * len(prompts)

    return judge_batch


def make_local_judge_text_batch(model: str | None = None, max_new_tokens: int = 1000):
    """BATCHED local judge returning RAW TEXT (not a Yes/No bool) — for CoT judges whose output
    needs custom parsing (e.g. PrivacyLens leakage 'Answer: Yes/No' after step-by-step reasoning,
    and helpfulness 'Answer: Poor/Unsatisfactory/Good/Excellent' = 0-3). GREEDY decode (temp 0) to
    match the source's VLLM temperature=0 and keep the judge deterministic on both the baseline and
    the per-iteration eval (parity). Fail-closed: any error -> '' per prompt (the caller parses '' as
    the conservative judgment for its metric)."""
    model_id = model or os.getenv("JUDGE_MODEL_LOCAL", "Qwen/Qwen2.5-7B-Instruct")
    holder: dict[str, object] = {}
    lock = threading.Lock()

    def _model():
        if "m" not in holder:
            from aar.eval_pod.models import HFModel
            logger.info("loading local TEXT-judge model: %s (greedy, max_new_tokens=%d)", model_id, max_new_tokens)
            m = HFModel(model_id, max_new_tokens=max_new_tokens)
            if hasattr(m, "apply_decoding"):
                m.apply_decoding(temperature=0.0)   # greedy == source VLLM temperature=0 (reproducible)
            holder["m"] = m
        return holder["m"]

    def judge_batch(prompts: list[str]) -> list[str]:
        if not prompts:
            return []
        try:
            with lock:
                return _model().generate_batch(prompts, max_new_tokens=max_new_tokens)
        except Exception as e:
            logger.warning("local text-judge error (-> '' for %d prompts): %s", len(prompts), e)
            return [""] * len(prompts)

    return judge_batch


def make_anthropic_judge_text_batch(model: str | None = None, max_tokens: int = 1000):
    """BATCHED Anthropic CoT judge returning RAW TEXT — a drop-in for make_local_judge_text_batch,
    backed by Claude (default claude-haiku-4-5) over CONCURRENT API calls (JUDGE_CONCURRENCY).
    Same return contract: prompts -> list[str] of raw CoT text the caller parses (e.g. PrivacyLens
    'Answer: Yes/No' leakage + 'Answer: Poor/Unsatisfactory/Good/Excellent' helpfulness). GREEDY
    (temperature 0) so the judge is deterministic + parity-identical at baseline and per-iteration
    eval. Fail-closed: any per-item error -> '' (the caller parses '' as the conservative judgment).
    Requires ANTHROPIC_API_KEY / ANT_high_prio_API / ANT_API_KEY."""
    import concurrent.futures
    from aar.benchmarks._judge_http import anthropic_chat, _anthropic_key
    model_id = model or os.getenv("JUDGE_MODEL", "claude-haiku-4-5")
    if not _anthropic_key():
        raise RuntimeError("anthropic text judge needs ANTHROPIC_API_KEY / ANT_high_prio_API / ANT_API_KEY")
    conc = int(os.getenv("JUDGE_CONCURRENCY", "12"))

    def judge_batch(prompts: list[str]) -> list[str]:
        if not prompts:
            return []
        out = [""] * len(prompts)

        def _one(i: int) -> None:
            try:
                out[i] = anthropic_chat([{"role": "user", "content": prompts[i]}],
                                        model=model_id, max_tokens=max_tokens, temperature=0.0)
            except Exception as e:
                logger.warning("anthropic text-judge error (-> '' for item %d): %s", i, e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=conc) as ex:
            list(ex.map(_one, range(len(prompts))))
        return out

    return judge_batch
