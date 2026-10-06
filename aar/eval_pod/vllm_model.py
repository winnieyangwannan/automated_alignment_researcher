"""High-throughput vLLM backend for target-model evaluation.

The benchmark-facing protocol intentionally matches :class:`HFModel`: generated
answers, summed candidate continuation log-probabilities, and length-normalized
completion log-probabilities.  vLLM receives every request in a benchmark at
once and uses its continuous scheduler to form device batches.

PEFT submissions are served as runtime LoRAs.  Some composite checkpoints are
loaded by Transformers with decoder names below ``model.layers`` but by vLLM
below ``model.language_model.layers``.  Such adapters are copied to a temporary
directory with the keys rewritten, then checked against the base model so a
silently ignored adapter can never receive a score.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import shutil
import tempfile
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

from aar.eval_pod.models import (
    _as_messages,
    _context_window,
    _ensure_str,
    _flatten_messages,
    split_reasoning_and_answer_text,
)


_ADAPTER_PROBE = (
    "Question: Is it ever acceptable to lie to a friend to spare their feelings?\nAnswer:",
    " It depends on the situation, but honesty usually serves a friendship better than a comforting lie.",
)

_NO_REPEAT_NGRAM_EXTRA_ARG = "aar_no_repeat_ngram_size"
_NO_REPEAT_NGRAM_PROCESSOR = (
    "aar.eval_pod.vllm_logits_processors:NoRepeatNGramAdapterLogitsProcessor"
)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _round_lora_rank(rank: int) -> int:
    """Return a vLLM-supported power-of-two capacity for an adapter rank."""
    capacity = 8
    while capacity < rank:
        capacity *= 2
    return capacity


def _is_heterogeneous_gemma4(model_config: Any) -> bool:
    """Return whether the checkpoint needs vLLM's heterogeneous Gemma-4 loader."""
    if getattr(model_config, "model_type", None) != "gemma4":
        return False
    text_config = getattr(model_config, "text_config", model_config)
    head_dim = getattr(text_config, "head_dim", None)
    global_head_dim = getattr(text_config, "global_head_dim", None)
    return (
        head_dim is not None
        and global_head_dim is not None
        and int(head_dim) != int(global_head_dim)
    )


def require_compatible_vllm(vllm_version: str, model_config: Any) -> None:
    """Fail quickly on vLLM releases that mis-load heterogeneous Gemma-4."""
    if not _is_heterogeneous_gemma4(model_config):
        return
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", vllm_version)
    if match is None:
        raise RuntimeError(
            "cannot verify vLLM compatibility for heterogeneous Gemma-4 from "
            f"version {vllm_version!r}; use the validated vLLM 0.25.1 image"
        )
    release = tuple(int(component) for component in match.groups())
    if release < (0, 25, 1):
        raise RuntimeError(
            "heterogeneous Gemma-4 requires vLLM >= 0.25.1; older releases "
            "construct 256-dimensional parameters for 512-dimensional global "
            f"attention weights (installed vLLM: {vllm_version})"
        )


def vllm_hf_overrides(model_config: Any) -> dict[str, Any]:
    """Allow vLLM's Gemma-4 converter to inspect heterogeneous dimensions.

    Transformers 5.17 requires consumers to opt in before reading a global
    value for a per-layer attribute. This narrow override permits inspection; a
    separate version gate requires the vLLM loader that actually preserves both
    the local and global dimensions.
    """
    text_config = getattr(model_config, "text_config", None)
    if text_config is not None and bool(
        getattr(text_config, "is_heterogeneous", False)
    ):
        return {
            "text_config": {
                "allow_global_per_layer_attribute_access": True,
            }
        }
    return {}


def vllm_lora_layout(
    tensors: dict[str, Any], config: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Translate text-only PEFT decoder keys to a composite vLLM layout."""
    renamed = {
        key.replace(".model.layers.", ".model.language_model.layers."): value
        for key, value in tensors.items()
    }
    targets = sorted(
        {
            key.split(".lora_")[0].rsplit(".", 1)[-1]
            for key in renamed
            if ".lora_" in key
        }
    )
    converted_config = dict(config)
    if targets:
        converted_config["target_modules"] = targets
    return renamed, converted_config


def prepare_vllm_adapter(
    adapter_path: str, model_config: Any
) -> tuple[str, str | None]:
    """Return the adapter path vLLM should load and an optional temp directory.

    ``EVAL_VLLM_LORA_LAYOUT=native`` disables composite-key conversion;
    ``language_model`` forces it.  The default, ``auto``, converts only when the
    base configuration has a nested text model and the adapter uses text-only
    ``model.layers`` names.
    """
    from safetensors.torch import load_file, save_file

    source = Path(adapter_path)
    weights = source / "adapter_model.safetensors"
    config_path = source / "adapter_config.json"
    if not weights.is_file() or not config_path.is_file():
        raise FileNotFoundError(
            "vLLM evaluation requires a PEFT safetensors adapter containing "
            f"adapter_model.safetensors and adapter_config.json: {source}"
        )

    tensors = load_file(weights)
    layout = os.getenv("EVAL_VLLM_LORA_LAYOUT", "auto").strip().lower()
    if layout not in ("auto", "native", "language_model"):
        raise ValueError(
            "EVAL_VLLM_LORA_LAYOUT must be auto, native, or language_model"
        )
    text_config = getattr(model_config, "text_config", None)
    has_text_only_keys = any(
        ".model.layers." in key and ".model.language_model.layers." not in key
        for key in tensors
    )
    convert = layout == "language_model" or (
        layout == "auto" and text_config is not None and has_text_only_keys
    )
    if not convert:
        return str(source), None

    config = json.loads(config_path.read_text())
    converted_tensors, converted_config = vllm_lora_layout(tensors, config)
    target = Path(tempfile.mkdtemp(prefix="aar-vllm-lora-"))
    save_file(converted_tensors, target / "adapter_model.safetensors")
    (target / "adapter_config.json").write_text(json.dumps(converted_config))
    target.chmod(0o755)
    print(f"[eval:vllm] translated LoRA layout {source} -> {target}", flush=True)
    return str(target), str(target)


class NoRepeatNGramLogitsProcessor:
    """Small vLLM-compatible no-repeat-ngram processor.

    vLLM releases have used both ``(token_ids, logits)`` and
    ``(prompt_ids, output_ids, logits)`` custom-processor call signatures.  The
    flexible call keeps the golden decoding guard working across those APIs.
    """

    def __init__(self, ngram_size: int) -> None:
        self.ngram_size = int(ngram_size)

    def __call__(self, *args):
        if len(args) == 2:
            token_ids, logits = args
        elif len(args) == 3:
            prompt_ids, output_ids, logits = args
            token_ids = [*list(prompt_ids), *list(output_ids)]
        else:  # pragma: no cover - defensive against an unsupported vLLM API
            raise TypeError(f"unexpected logits-processor arguments: {len(args)}")
        ids = token_ids.tolist() if hasattr(token_ids, "tolist") else list(token_ids)
        n = self.ngram_size
        if n <= 0 or len(ids) + 1 < n:
            return logits
        prefix = tuple(ids[-(n - 1):]) if n > 1 else ()
        banned: set[int] = set()
        for start in range(0, len(ids) - n + 1):
            if n == 1 or tuple(ids[start:start + n - 1]) == prefix:
                banned.add(int(ids[start + n - 1]))
        if banned:
            logits[list(banned)] = -float("inf")
        return logits


class VLLMModel:
    """An in-process vLLM engine satisfying the evaluator's ``Model`` protocol."""

    def __init__(self, model_path: str, max_new_tokens: int | None = None):
        from transformers import AutoConfig, AutoProcessor, AutoTokenizer, GenerationConfig

        os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
        from vllm import LLM, SamplingParams

        vllm_version = package_version("vllm")

        self._SamplingParams = SamplingParams
        sampling_parameters = inspect.signature(SamplingParams).parameters
        self._vllm_v1_logits_processors = "extra_args" in sampling_parameters
        self._vllm_legacy_logits_processors = (
            "logits_processors" in sampling_parameters
        )
        submitted = Path(model_path)
        is_adapter = (submitted / "adapter_config.json").is_file()
        adapter_config: dict[str, Any] = {}
        base_model_ref = model_path
        if is_adapter:
            adapter_config = json.loads(
                (submitted / "adapter_config.json").read_text()
            )
            base_model_ref = (
                os.getenv("TARGET_MODEL_PATH")
                or adapter_config.get("base_model_name_or_path")
            )
            if not base_model_ref:
                raise ValueError(
                    f"adapter submission {model_path!r} does not identify a base model"
                )

        self.config = AutoConfig.from_pretrained(base_model_ref)
        require_compatible_vllm(vllm_version, self.config)
        strategy = os.getenv("EVAL_VLLM_LORA_STRATEGY", "").strip()
        if strategy not in ("", "base", "merged_checkpoint", "runtime_lora"):
            raise ValueError(
                "EVAL_VLLM_LORA_STRATEGY must be base, merged_checkpoint, or "
                "runtime_lora"
            )
        expected_strategy = "runtime_lora" if is_adapter else (
            "merged_checkpoint"
            if (submitted / ".merge-complete.json").is_file()
            else "base"
        )
        if strategy and strategy != expected_strategy:
            raise RuntimeError(
                f"vLLM LoRA strategy mismatch: requested {strategy!r}, model "
                f"path requires {expected_strategy!r}"
            )
        strategy = strategy or expected_strategy
        if _env_bool("EVAL_VLLM_REQUIRE_MERGED", False) and strategy != "merged_checkpoint":
            raise RuntimeError(
                "EVAL_VLLM_REQUIRE_MERGED=1 requires a checkpoint containing "
                ".merge-complete.json"
            )
        tokenizer_ref = model_path if is_adapter else base_model_ref
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_ref)
        except Exception:
            tokenizer_ref = base_model_ref
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_ref)
            except Exception:
                self.tokenizer = AutoProcessor.from_pretrained(tokenizer_ref).tokenizer
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        native_context = _context_window(self.config, self.tokenizer)
        configured_context = int(os.getenv("EVAL_VLLM_MAX_MODEL_LEN", "65536"))
        self._ctx = min(native_context, configured_context)
        env_mnt = os.getenv("EVAL_MAX_NEW_TOKENS")
        self.max_new_tokens = (
            max_new_tokens
            if max_new_tokens is not None
            else (int(env_mnt) if env_mnt else None)
        )
        self._auto_ceiling = int(os.getenv("EVAL_AUTO_CEILING", "2048"))
        self.batch_size = int(os.getenv("EVAL_BATCH_SIZE", "16"))
        self._no_repeat_ngram = int(os.getenv("EVAL_NO_REPEAT_NGRAM", "0"))
        self._temperature = float(os.getenv("EVAL_TEMPERATURE", "1.0"))
        self._top_p = float(os.getenv("EVAL_TOP_P", "1.0"))
        self._seed = int(os.getenv("EVAL_SEED", "1234"))
        self._enable_thinking = _env_bool("AAR_TARGET_ENABLE_THINKING", False)
        self._generation_count = 0
        self._trunc_count = 0
        self._oom_count = 0
        self._allocator_warning_count = 0
        self._adapter_temp_dir: str | None = None
        self._closed = False

        stop_ids: set[int] = set()

        def add_stop_ids(value: Any) -> None:
            if value is None:
                return
            values = value if isinstance(value, (list, tuple)) else [value]
            stop_ids.update(int(item) for item in values if item is not None)

        add_stop_ids(getattr(self.config, "eos_token_id", None))
        add_stop_ids(self.tokenizer.eos_token_id)
        try:
            generation_config = GenerationConfig.from_pretrained(base_model_ref)
            add_stop_ids(generation_config.eos_token_id)
        except Exception:
            pass
        self._stop_ids = sorted(stop_ids)

        adapter_path = None
        if is_adapter:
            adapter_path, self._adapter_temp_dir = prepare_vllm_adapter(
                model_path, self.config
            )

        engine_kwargs: dict[str, Any] = {
            "model": base_model_ref,
            "tokenizer": tokenizer_ref,
            "trust_remote_code": _env_bool("EVAL_VLLM_TRUST_REMOTE_CODE", True),
            "dtype": "bfloat16",
            "max_model_len": self._ctx,
            "gpu_memory_utilization": float(
                os.getenv("EVAL_VLLM_GPU_MEMORY_UTILIZATION", "0.80")
            ),
            "max_num_seqs": int(os.getenv("EVAL_VLLM_MAX_NUM_SEQS", "256")),
            "enable_prefix_caching": _env_bool(
                "EVAL_VLLM_ENABLE_PREFIX_CACHING", True
            ),
            "enforce_eager": _env_bool("EVAL_VLLM_ENFORCE_EAGER", False),
            "disable_log_stats": True,
        }
        if self._vllm_v1_logits_processors:
            # vLLM >= 0.20 registers processor classes once on the engine and
            # enables them per request through SamplingParams.extra_args.
            engine_kwargs["logits_processors"] = [_NO_REPEAT_NGRAM_PROCESSOR]
        if _is_heterogeneous_gemma4(self.config):
            # The validated steerability deployment serves this composite
            # checkpoint as a text model. Avoid loading/profiling the unused
            # vision encoder and match its known-good vLLM configuration.
            engine_kwargs["language_model_only"] = True
        hf_overrides = vllm_hf_overrides(self.config)
        if hf_overrides:
            engine_kwargs["hf_overrides"] = hf_overrides
        if is_adapter:
            engine_kwargs.update(
                enable_lora=True,
                max_loras=1,
                max_cpu_loras=1,
                max_lora_rank=_round_lora_rank(int(adapter_config.get("r", 8))),
            )
        print(
            "[eval:vllm] runtime "
            f"backend=vllm version={vllm_version} "
            f"language_model_only={engine_kwargs.get('language_model_only', False)} "
            f"model={base_model_ref} lora_strategy={strategy}",
            flush=True,
        )
        print(
            "[eval:vllm] loading "
            f"{base_model_ref} max_model_len={self._ctx} "
            f"max_num_seqs={engine_kwargs['max_num_seqs']} "
            f"prefix_caching={engine_kwargs['enable_prefix_caching']} "
            f"lora={is_adapter}",
            flush=True,
        )
        try:
            self.llm = LLM(**engine_kwargs)
        except Exception:
            if self._adapter_temp_dir:
                shutil.rmtree(self._adapter_temp_dir, ignore_errors=True)
            raise

        self._lora_request = None
        if adapter_path:
            from vllm.lora.request import LoRARequest

            self._lora_request = LoRARequest("aar-eval-adapter", 1, adapter_path)
            if _env_bool("EVAL_VLLM_VERIFY_LORA", True):
                try:
                    self._verify_lora_changes_predictions()
                except Exception:
                    self.close()
                    raise

    def apply_decoding(
        self,
        *,
        batch_size=None,
        auto_ceiling=None,
        no_repeat_ngram=None,
        max_new_tokens="__keep__",
        temperature=None,
        top_p=None,
        seed=None,
    ) -> None:
        if batch_size is not None:
            self.batch_size = int(batch_size)
        if auto_ceiling is not None:
            self._auto_ceiling = int(auto_ceiling)
        if no_repeat_ngram is not None:
            self._no_repeat_ngram = int(no_repeat_ngram)
        if max_new_tokens != "__keep__":
            self.max_new_tokens = (
                int(max_new_tokens) if max_new_tokens is not None else None
            )
        if temperature is not None:
            self._temperature = float(temperature)
        if top_p is not None:
            self._top_p = float(top_p)
        if seed is not None:
            self._seed = int(seed)

    def _render(
        self,
        prompt,
        use_chat_template: bool = True,
        enable_thinking: bool | None = None,
    ) -> str:
        if not use_chat_template:
            return (
                prompt
                if isinstance(prompt, str)
                else _flatten_messages(_as_messages(prompt))
            )
        if enable_thinking is None:
            enable_thinking = self._enable_thinking
        messages = _as_messages(prompt)
        kwargs = {"tokenize": False, "add_generation_prompt": True}
        if enable_thinking:
            kwargs["enable_thinking"] = True
        try:
            return _ensure_str(self.tokenizer.apply_chat_template(messages, **kwargs))
        except Exception:
            flattened = _flatten_messages(messages)
            try:
                return _ensure_str(
                    self.tokenizer.apply_chat_template(
                        [{"role": "user", "content": flattened}], **kwargs
                    )
                )
            except Exception:
                return flattened

    def _budget(self, input_len: int, override=None) -> int:
        remaining = max(1, self._ctx - int(input_len) - 16)
        if override is not None:
            return min(int(override), remaining)
        if self.max_new_tokens is not None:
            return min(self.max_new_tokens, remaining)
        return max(1, min(remaining, self._auto_ceiling))

    def _sampling_params(self, max_tokens: int, *, prompt_logprobs=None):
        kwargs: dict[str, Any] = {
            "max_tokens": int(max_tokens),
            "temperature": max(0.0, self._temperature),
            "top_p": self._top_p,
            "seed": self._seed,
            "stop_token_ids": self._stop_ids,
            "skip_special_tokens": False,
        }
        if prompt_logprobs is not None:
            kwargs.update(temperature=0.0, prompt_logprobs=prompt_logprobs)
        if self._no_repeat_ngram > 0 and prompt_logprobs is None:
            if self._vllm_v1_logits_processors:
                kwargs["extra_args"] = {
                    _NO_REPEAT_NGRAM_EXTRA_ARG: self._no_repeat_ngram
                }
            elif self._vllm_legacy_logits_processors:
                kwargs["logits_processors"] = [
                    NoRepeatNGramLogitsProcessor(self._no_repeat_ngram)
                ]
            else:
                raise RuntimeError(
                    "this vLLM version does not expose a supported custom "
                    "logits-processor API for no_repeat_ngram"
                )
        return self._SamplingParams(**kwargs)

    def _run(self, prompt_ids: list[list[int]], params, *, use_lora: bool = True):
        prompts = [{"prompt_token_ids": ids} for ids in prompt_ids]
        return self.llm.generate(
            prompts,
            params,
            use_tqdm=False,
            lora_request=self._lora_request if use_lora else None,
        )

    def _decode_completion(self, token_ids: list[int]) -> str:
        raw = self.tokenizer.decode(token_ids, skip_special_tokens=False)
        reasoning, answer = split_reasoning_and_answer_text(raw)
        if reasoning:
            return answer
        return self.tokenizer.decode(token_ids, skip_special_tokens=True).strip()

    def generate(self, prompt, **kwargs) -> str:
        return self.generate_batch([prompt], **kwargs)[0]

    def generate_batch(self, prompts: list[str], **kwargs) -> list[str]:
        if not prompts:
            return []
        rendered = [self._render(prompt, True) for prompt in prompts]
        prompt_ids = [self.tokenizer(text).input_ids for text in rendered]
        max_tokens = self._budget(
            max(map(len, prompt_ids)), kwargs.get("max_new_tokens")
        )
        outputs = self._run(prompt_ids, self._sampling_params(max_tokens))
        answers: list[str] = []
        for request in outputs:
            completion = request.outputs[0]
            token_ids = list(completion.token_ids)
            self._generation_count += 1
            if getattr(completion, "finish_reason", None) == "length":
                self._trunc_count += 1
            answers.append(self._decode_completion(token_ids))
        return answers

    @staticmethod
    def _logprob_value(entry: Any, token_id: int) -> float:
        if entry is None:
            raise RuntimeError("vLLM omitted a required prompt log-probability")
        value = entry.get(token_id)
        if value is None:
            value = entry.get(str(token_id))
        if value is None:
            raise RuntimeError(
                f"vLLM prompt log-probabilities omitted chosen token {token_id}"
            )
        return float(getattr(value, "logprob", value))

    def _sequence_logprobs(
        self,
        sequences: list[list[int]],
        spans: list[tuple[int, list[int]]],
        *,
        use_lora: bool = True,
    ) -> list[list[float]]:
        if not sequences:
            return []
        outputs = self._run(
            sequences,
            self._sampling_params(1, prompt_logprobs=0),
            use_lora=use_lora,
        )
        values: list[list[float]] = []
        for request, (start, token_ids) in zip(outputs, spans, strict=True):
            prompt_logprobs = request.prompt_logprobs
            values.append(
                [
                    self._logprob_value(prompt_logprobs[start + offset], token_id)
                    for offset, token_id in enumerate(token_ids)
                ]
            )
        return values

    def candidate_logits(
        self,
        prompt: str,
        candidates: list[str],
        use_chat_template: bool = True,
    ) -> list[float]:
        return self.candidate_logits_batch(
            [prompt], candidates, use_chat_template
        )[0]

    def candidate_logits_batch(
        self,
        prompts: list[str],
        candidates: list[str],
        use_chat_template: bool = True,
    ) -> list[list[float]]:
        candidate_ids = [
            self.tokenizer.encode(candidate, add_special_tokens=False)
            for candidate in candidates
        ]
        sequences: list[list[int]] = []
        spans: list[tuple[int, list[int]]] = []
        for prompt in prompts:
            prompt_ids = self.tokenizer(
                self._render(prompt, use_chat_template, enable_thinking=False)
            ).input_ids
            for ids in candidate_ids:
                sequences.append([*prompt_ids, *ids])
                spans.append((len(prompt_ids), ids))
        flat = self._sequence_logprobs(sequences, spans)
        scores: list[list[float]] = []
        width = len(candidates)
        for start in range(0, len(flat), width):
            scores.append([sum(values) for values in flat[start:start + width]])
        return scores

    def completion_logprob_batch(
        self,
        prompts: list[str],
        completions: list[str],
        use_chat_template: bool = False,
    ) -> list[float]:
        sequences: list[list[int]] = []
        spans: list[tuple[int, list[int]]] = []
        for prompt, completion in zip(prompts, completions, strict=True):
            context = self._render(prompt, use_chat_template)
            context_ids = self.tokenizer(context).input_ids
            full_ids = self.tokenizer(context + completion).input_ids
            prompt_len = len(context_ids)
            while prompt_len > 0 and full_ids[:prompt_len] != context_ids[:prompt_len]:
                prompt_len -= 1
            completion_ids = full_ids[prompt_len:]
            sequences.append(full_ids)
            spans.append((prompt_len, completion_ids))
        token_logprobs = self._sequence_logprobs(sequences, spans)
        return [
            sum(values) / len(values) if values else float("-inf")
            for values in token_logprobs
        ]

    def _verify_lora_changes_predictions(self) -> None:
        prompt_ids = self.tokenizer(_ADAPTER_PROBE[0]).input_ids
        completion_ids = self.tokenizer.encode(
            _ADAPTER_PROBE[1], add_special_tokens=False
        )
        sequence = [*prompt_ids, *completion_ids]
        span = [(len(prompt_ids), completion_ids)]
        base = self._sequence_logprobs([sequence], span, use_lora=False)[0]
        adapted = self._sequence_logprobs([sequence], span, use_lora=True)[0]
        effect = sum(abs(left - right) for left, right in zip(base, adapted, strict=True)) / len(base)
        print(
            f"[eval:vllm] LoRA check mean |dlogp|={effect:.6g}", flush=True
        )
        if effect <= float(os.getenv("EVAL_VLLM_MIN_LORA_EFFECT", "1e-5")):
            raise RuntimeError(
                "vLLM accepted the LoRA adapter but it did not change the model's "
                "predictions. Refusing to silently evaluate the base model; check "
                "EVAL_VLLM_LORA_LAYOUT or set EVAL_VLLM_VERIFY_LORA=0 only after "
                "an independent adapter-equivalence check."
            )

    def evaluation_health(self) -> dict[str, int]:
        return {
            "generated": self._generation_count,
            "truncated": self._trunc_count,
            "allocator_warnings": self._allocator_warning_count,
            "ooms": self._oom_count,
        }

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        engine = getattr(self, "llm", None)
        if engine is not None:
            shutdown = getattr(engine, "shutdown", None)
            if callable(shutdown):
                shutdown()
            else:
                inner = getattr(engine, "llm_engine", None)
                inner_shutdown = getattr(inner, "shutdown", None)
                if callable(inner_shutdown):
                    inner_shutdown()
        if self._adapter_temp_dir:
            shutil.rmtree(self._adapter_temp_dir, ignore_errors=True)

    def __del__(self):  # pragma: no cover - interpreter shutdown is implementation-specific
        try:
            self.close()
        except Exception:
            pass
