#!/usr/bin/env python3
"""Download a Hugging Face model into a shared cache and smoke-test GPU generation."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--revision", default="main")
    parser.add_argument("--cache-dir", default=os.environ.get("HF_HOME"))
    parser.add_argument(
        "--prompt", default="Write one short sentence confirming GPU inference works."
    )
    parser.add_argument("--new-tokens", type=int, default=32)
    parser.add_argument("--warmup-tokens", type=int, default=4)
    parser.add_argument(
        "--dtype", choices=("bfloat16", "float16", "float32"), default="bfloat16"
    )
    parser.add_argument(
        "--model-class", choices=("auto", "causal", "image-text"), default="auto"
    )
    parser.add_argument("--require-import", action="append", default=[])
    parser.add_argument("--min-tokens-per-second", type=float)
    parser.add_argument("--max-generation-seconds", type=float)
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    if not args.cache_dir:
        parser.error("set HF_HOME or pass --cache-dir")
    if args.new_tokens < 1 or args.warmup_tokens < 0:
        parser.error("token counts must be positive (warmup may be zero)")
    return args


def main() -> int:
    args = parse_args()
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(cache_dir)

    import torch
    from huggingface_hub import snapshot_download
    from transformers import (
        AutoConfig,
        AutoModelForCausalLM,
        AutoModelForImageTextToText,
        AutoProcessor,
        AutoTokenizer,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available to PyTorch")
    for module_name in args.require_import:
        importlib.import_module(module_name)

    download_started = time.perf_counter()
    snapshot = Path(
        snapshot_download(repo_id=args.model, revision=args.revision)
    ).resolve()
    download_seconds = time.perf_counter() - download_started
    if not snapshot.is_relative_to(cache_dir):
        raise RuntimeError(f"snapshot escaped cache directory: {snapshot}")

    config = AutoConfig.from_pretrained(
        snapshot, local_files_only=True, trust_remote_code=args.trust_remote_code
    )
    architectures = " ".join(getattr(config, "architectures", None) or [])
    model_class = args.model_class
    if model_class == "auto":
        model_class = "image-text" if "ConditionalGeneration" in architectures else "causal"
    if model_class == "image-text":
        processor = AutoProcessor.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=args.trust_remote_code
        )
        loader = AutoModelForImageTextToText
    else:
        processor = AutoTokenizer.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=args.trust_remote_code
        )
        loader = AutoModelForCausalLM

    dtype = getattr(torch, args.dtype)
    load_started = time.perf_counter()
    model = loader.from_pretrained(
        snapshot,
        local_files_only=True,
        trust_remote_code=args.trust_remote_code,
        dtype=dtype,
    ).to("cuda").eval()
    load_seconds = time.perf_counter() - load_started

    messages = [{"role": "user", "content": args.prompt}]
    if hasattr(processor, "apply_chat_template") and getattr(
        processor, "chat_template", None
    ):
        prompt = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        prompt = args.prompt
    inputs = processor(text=prompt, return_tensors="pt").to("cuda")
    input_tokens = inputs.input_ids.shape[-1]

    def generate(count: int):
        return model.generate(
            **inputs,
            do_sample=False,
            min_new_tokens=count,
            max_new_tokens=count,
        )

    with torch.inference_mode():
        if args.warmup_tokens:
            generate(args.warmup_tokens)
            torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        generation_started = time.perf_counter()
        output = generate(args.new_tokens)
        torch.cuda.synchronize()
        generation_seconds = time.perf_counter() - generation_started

    generated_tokens = output.shape[-1] - input_tokens
    tokens_per_second = generated_tokens / generation_seconds
    text = processor.batch_decode(output[:, input_tokens:], skip_special_tokens=True)[0]
    snapshot_bytes = sum(path.stat().st_size for path in snapshot.rglob("*") if path.is_file())
    passed = True
    if args.min_tokens_per_second is not None:
        passed &= tokens_per_second >= args.min_tokens_per_second
    if args.max_generation_seconds is not None:
        passed &= generation_seconds <= args.max_generation_seconds

    result = {
        "passed": passed,
        "model": args.model,
        "revision": snapshot.name,
        "snapshot": str(snapshot),
        "snapshot_gib": round(snapshot_bytes / 1024**3, 3),
        "device": torch.cuda.get_device_name(0),
        "compute_capability": ".".join(map(str, torch.cuda.get_device_capability(0))),
        "dtype": str(dtype),
        "required_imports": args.require_import,
        "download_seconds": round(download_seconds, 3),
        "load_seconds": round(load_seconds, 3),
        "generation_seconds": round(generation_seconds, 3),
        "generated_tokens": generated_tokens,
        "tokens_per_second": round(tokens_per_second, 3),
        "peak_gpu_gib": round(torch.cuda.max_memory_allocated() / 1024**3, 3),
        "output": text,
    }
    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    print(rendered)
    if args.output_json:
        output_path = Path(args.output_json).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
