# Run 9 setup

Run 9 is a five-success AutoData-assisted AAR experiment for improving honesty,
sycophancy resistance, and uncertainty disclosure in Gemma-4 31B. Five
successes means five durable score/result pairs from one sequential research
chain, not five research chains running in parallel.

## System topology

```text
One sequential outer AAR chain
  Claude Opus 4.8 researcher
    → AutoData design and three-round strategy optimization
      → Kimi-K2.6 generates candidate training examples
      → Gemma-4-31B-it answers each prompt in target-aware mode
      → GPT-5.6 Luna judges teacher quality and target challenge
    → production dataset
    → LoRA SFT of Gemma-4-31B-it
    → merged checkpoint served by vLLM 0.25.1
    → protected evaluation
    → next sequential AAR iteration
```

The chain may use up to eight research sessions to obtain five successful
score/result pairs. Failed sessions do not count as successes. The protected
evaluator is a separate Slurm allocation and is not a second research chain.

## Model roles

- **Research agent:** `claude-opus-4-8`. It proposes the method, authors the
  AutoData workspace, interprets permitted results, and advances the outer AAR
  loop.
- **Approval monitor:** `claude-opus-4-8` by default for the full chain. It
  reviews method proposals and delegated AutoData approval actions. This role
  is separate from row-level data judging.
- **Generator/teacher:** `Kimi-K2.6`, routed through deployment
  `winnieyangwn-kimi26`. It creates synthetic prompts and ideal responses.
- **Target/student:** `google/gemma-4-31B-it`. Target-aware generation probes
  the exact pinned research-side deployment to identify prompts on which the
  current checkpoint exhibits the intended failure. LoRA SFT then trains this
  model on the accepted examples.
- **Data judge:** `gpt-5-6-luna`. It checks the Kimi response and, in
  target-aware mode, verifies that Gemma's failure matches the example's
  primary alignment axis.
- **Evaluation judge:** `gpt-5-6-luna` for the applicable model-judged and MASK
  components of the protected evaluation.
- **Inference runtime:** vLLM `0.25.1`. Candidate adapters are atomically merged
  into separate Gemma checkpoints before evaluation; runtime vLLM LoRA is not
  substituted.

## Parallelism

- Outer research chains: **1**.
- Sequential successful AAR iterations requested: **5**.
- Maximum research sessions allowed: **8**, providing room for failed attempts.
- AutoData broker concurrency inside a new question-only chain: **64 tasks**.
- AutoData broker: one campaign-scoped `local-bwrap` broker on the allocated CPU
  Slurm node.
- AutoData's native execution JSON still names the broker-client adapter
  `sandoq-firecracker` and retains an `oci-runner-firecracker-large` environment
  label. Neither field identifies the physical runner; verify
  `metadata/autodata-campaign-policy.json` or the broker startup log instead.
- Training and protected evaluation are downstream stages; they do not create
  additional research chains.

The original launch created two long-lived Slurm allocations:

- `1780610`: research agent, AutoData lifecycle, and local broker.
- `1780609`: protected evaluator worker.

Job IDs are attempt-specific operational metadata, not reusable configuration.

## AutoData budget and dataset shape

- Tuning tasks: **64**.
- Hidden AutoData validation tasks: **32**.
- AutoData test tasks: **32**.
- Inner generation-strategy meta-optimization rounds: **3**.
- Initial production source tasks: **1,250**.
- Required retained judge-accepted rows: **1,000**.
- Production source-task ceiling: **2,000** when additional headroom is needed.
- Per-execution task concurrency: **64** for the validated question-only
  Kimi-to-Luna path. Target-probing deployments must pass their own capacity
  canary and may override this setting downward.
- Production completion: **1,000 accepted rows** and at least **95% successful
  source-task coverage** after a complete corpus pass.
- Required AutoData revision for new launches:
  `823c5948854df14664f3168bc5e6c49a2cecb975`.

The intended target-aware row flow is:

```text
grounded scenario
  → Kimi prompt and teacher response
  → pinned Gemma target response
  → Luna teacher-quality and target-challenge judgment
  → accept only a high-quality row that exposes the matching Gemma weakness
```

Every accepted target-aware row records generator, target, and judge usage,
including the target deployment and checkpoint hash. Raw protected evaluator
inputs are never visible to AutoData or the research agent.

## Active legacy-ablation caveat

The production execution active on 2026-10-09 is an explicitly approved legacy
SFT ablation. It uses the older `run9-anchored-v1` Kimi-to-Luna flow without a
Gemma target probe. It tests whether the legacy synthetic SFT data is
structurally trainable and useful, but it is not equivalent to normal
target-aware Run 9 production and must not be counted as one of the five
target-aware confirmations.

The five-minute real-GPU smoke confirmed that the legacy data can train Gemma:
one row completed tokenization, a forward/backward LoRA optimizer step, and a
reloadable adapter save. The generated method required a small compatibility
fix because Gemma's tokenizer returned a Transformers `BatchEncoding` rather
than a plain token-ID list.

## Related documentation

- [AAR run plan](aar_run_plan.md)
- [AutoData design](autodata.md)
- [Implementation changes](implementation_changes.md)
- [Stage timing](stage_timing.md)
- [Progress log](run_9_progress.md)
