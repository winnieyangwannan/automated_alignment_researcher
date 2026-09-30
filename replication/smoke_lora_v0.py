#!/usr/bin/env python3
"""One-step Gemma-4 LoRA train/save/reload smoke for a GB300 allocation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForImageTextToText, AutoTokenizer

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable")
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForImageTextToText.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        attn_implementation="sdpa",
    ).to("cuda")
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model = get_peft_model(
        model,
        LoraConfig(
            r=4,
            lora_alpha=8,
            lora_dropout=0.0,
            # A broad q_proj/v_proj suffix also matches Gemma-4's vision
            # Gemma4ClippableLinear wrappers, which PEFT cannot wrap. Restrict
            # adapters to ordinary Linear layers in the language tower.
            target_modules=(
                r"model\.language_model\.layers\.\d+\.self_attn\."
                r"(q_proj|v_proj)"
            ),
            task_type="CAUSAL_LM",
        ),
    )
    messages = [
        {"role": "user", "content": "State the result of two plus two."},
        {"role": "assistant", "reasoning": "Add the two integers.", "content": "4"},
    ]
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, enable_thinking=True
    )
    batch = tokenizer(text, return_tensors="pt").to("cuda")
    model.train()
    loss = model(**batch, labels=batch["input_ids"]).loss
    loss.backward()
    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad), lr=1e-5
    )
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)

    args.output.mkdir(parents=True, exist_ok=False)
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    base = model.unload()
    reloaded = PeftModel.from_pretrained(base, args.output).eval()
    assert any(args.output.glob("adapter_model*.safetensors"))
    assert (args.output / "adapter_config.json").is_file()
    with torch.inference_mode():
        check = reloaded(**batch).logits[:, -1, :8]
    assert torch.isfinite(check).all()
    print(json.dumps({
        "ok": True,
        "device": torch.cuda.get_device_name(0),
        "loss": float(loss.detach()),
        "output": str(args.output),
    }, indent=2))


if __name__ == "__main__":
    main()
