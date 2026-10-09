# Run 11 design notes: five parallel AAR chains and target-aware data creation

Status: proposed design, not yet launched or capacity-validated.

This document records the intended design for a faster Run 11. It combines five
independent AAR chains with target-aware AutoData generation, while preserving the
research/evaluator isolation boundary. Run 7 is the precedent for five-chain
evaluation; Run 9 is the source of the local-Bubblewrap and target-probing work.

## Goals

- Run five independent AAR research chains without making their state or failures
  depend on one another.
- Share expensive model-serving capacity where doing so is safe.
- Let AutoData test whether generated examples actually expose undesirable behavior
  in the current Gemma parent model.
- Keep hidden evaluation data, evaluator credentials, and full held-out results out
  of every research-visible service.
- Measure queueing and stage latency so additional capacity is added at the actual
  bottleneck rather than by guesswork.

## Proposed architecture

```text
                           shared research services
                 +----------------------------------------+
                 | load-balanced Kimi replicas            |
                 | Luna judging service                   |
                 | elastic research-side Gemma targets    |
                 +-------------------+--------------------+
                                     |
          global limits, fairness, backpressure, and observability
                                     |
       +---------------+-------------+-------------+---------------+
       |               |             |             |               |
   AAR chain 1     AAR chain 2   AAR chain 3   AAR chain 4     AAR chain 5
   local broker    local broker  local broker  local broker    local broker
   private state   private state private state private state   private state
       |               |             |             |               |
       +---------------+-------------+-------------+---------------+
                                     |
                         training/admission scheduler
                                     |
                  protected shared evaluator claim queue
                                     |
                      five elastic Gemma evaluator lanes
```

Each chain owns a distinct attempt directory, AutoData workspace, broker process,
node-local SQLite ledger, ports, idempotency namespace, budgets, and candidate
history. The chains may share stateless model services, but must not share SQLite
files or mutable AutoData state.

## Five-chain precedent and evaluation topology

[Run 7](../run_7/README.md) already used five chains (`alpha` through `epsilon`),
five evaluator jobs, five concurrent training slots, and four GB300 GPUs per
evaluator job. Evaluators formed a shared atomic-claim pool: a free evaluator
claimed the next candidate rather than being permanently assigned to one chain.
Within a lane, one candidate's 13 benchmarks were distributed across four local
vLLM replicas.

Run 11 should retain this elastic claim-queue pattern. It handles unequal chain
speeds better than a fixed chain-to-evaluator mapping and avoids leaving a lane idle
only because its paired chain is still researching or training.

The existing evaluator processes are **not** general-purpose HTTP endpoints. They
run protected evaluation in process and have access to evaluator-only material.
AutoData must not call them. Run 11 may reuse their serving stack—validated vLLM
image, merged checkpoints, four-GPU configuration, Slurm scheduling, and health
checks—but not the protected processes, credentials, or hidden inputs.

## Target-aware AutoData generation

The intended per-example flow is:

```text
Kimi creates a candidate prompt and ideal teacher response
  -> the current Gemma parent answers the prompt through a research endpoint
  -> Luna judges both:
       1. teacher quality; and
       2. whether Gemma materially failed on the target behavior
  -> AutoData accepts/rejects the row and records quality/challenge metadata
```

This closes a gap in Luna-only generation: a clean, relevant teacher response does
not prove that the example is difficult or useful for the current Gemma model.

The recipe requires an all-or-none target configuration by default:

```text
AUTODATA_TARGET_URL
AUTODATA_TARGET_MODEL
AUTODATA_TARGET_DEPLOYMENT_ID
AUTODATA_TARGET_CHECKPOINT_HASH
```

It also supports an optional target host header and target-specific timeout, token,
and rate settings. Missing or partial configuration must fail closed. An explicit
`AUTODATA_TARGET_ENABLED=0` escape hatch is reserved for smoke tests and legacy
comparisons; a normal Run 11 chain must not use it. The checkpoint hash, deployment
ID, model name, server identity, decoding settings, and seed must be retained with
the run's reproducibility metadata.

Current target-aware acceptance requires both:

1. full performance on the task's one declared primary teacher dimension, with the
   remaining dimensions passing as universal or supporting guardrails and weighted
   teacher quality of at least `0.75`; and
2. a target challenge score above zero whose failure mode matches that primary
   axis: honesty → `dishonesty`, sycophancy resistance → `sycophancy`, or
   uncertainty disclosure → `concealed_uncertainty`.

The accepted training row contains the generated prompt and ideal response. The raw
Gemma probe response is not copied into the training dataset. Challenge evidence and
target provenance are retained as metadata.

### Target checkpoint routing

At AAR iteration 0, all chains start from the same base Gemma model. One shared,
load-balanced, multi-replica research deployment can therefore serve all five
chains.

After training begins, the chains can have different current-best checkpoints. Each
chain's AutoData phase should probe the **parent/current-best checkpoint used to
create the next child**, not a child that does not yet exist. The serving layer must
therefore route by an immutable checkpoint identity and may need as many as five
logical target deployments. A checkpoint-aware elastic pool is preferable to five
permanently reserved deployments when some chains are training or evaluating.

Never silently route to a different checkpoint. A request must fail if the served
model identity does not match the expected deployment ID and checkpoint hash.

## Isolation boundary

```markdown
| Component                  | May see research prompts | May see hidden evaluation data | Shared across chains |
| -------------------------- | ------------------------ | ------------------------------ | -------------------- |
| Kimi generation service    | Yes                      | No                             | Yes                  |
| Luna generation judge      | Yes                      | No                             | Yes                  |
| Research Gemma target      | Yes                      | No                             | Yes, by checkpoint   |
| Chain-local AutoData       | Its own state            | No                             | No mutable state     |
| Protected evaluator lane   | Candidate plus eval data | Yes                            | Claim queue only     |
```

The research target service must use research-only authentication and inputs. It
must not expose held-out prompts, aggregate held-out scores, evaluator logs, or
evaluator credentials. Physical GPUs may be time-multiplexed between research and
protected evaluation only through separate jobs/processes with clean state and
credentials.

## Capacity and concurrency plan

Run 9 validated approximately 16 concurrent local-Bubblewrap tasks for one chain;
it did not validate 80 simultaneous tasks. Starting five chains at 16 each would
also synchronize bursts against Kimi, Luna, and the Gemma target.

Initial Run 11 limits should be:

```markdown
| Limit                              | Initial value | Reason                                      |
| ---------------------------------- | ------------- | ------------------------------------------- |
| AutoData concurrency per chain     | 8             | Contains each chain's burst                 |
| Global AutoData in-flight limit    | 32            | Stays near tested single-node scale         |
| Concurrent training jobs           | Up to 5       | Matches the five-chain precedent            |
| Protected evaluator lanes          | Up to 5       | Elastic shared claim queue                  |
| Active target checkpoints          | Demand-driven | Avoids reserving 20 additional GPUs at idle |
```

The global controller needs fair admission, so one chain cannot occupy every Kimi,
Luna, or target-model slot. Stagger chain starts and production bursts. Increase the
global limit to 48 and then 64 only after aggregate canaries show acceptable p95
latency, error rates, queue time, and node utilization.

Do not add Kimi or Gemma replicas merely because end-to-end generation is slow.
First distinguish:

- local scheduler/SQLite contention;
- admission-queue delay;
- Kimi generation latency and rate limiting;
- Gemma target queue and inference latency;
- Luna judging latency and rate limiting; and
- retries, invalid outputs, or a low acceptance rate.

Five permanently active four-GPU research targets plus five four-GPU evaluator
lanes could consume 40 GPUs before training. Prefer elastic allocation or temporal
multiplexing unless measurements justify that cost.

## State, idempotency, and recovery

- Give every chain and attempt a unique namespace for job IDs and result paths.
- Keep the broker ledger on the broker's node-local disk; never put a shared SQLite
  database on network storage.
- Make generation jobs idempotent so retries cannot duplicate accepted rows.
- Retain target checkpoint identity on every judged row and reject stale results
  returned after a chain advances to a new parent checkpoint.
- Permit a failed chain to restart from its own durable boundary without cancelling
  other chains.
- Apply both per-chain and global budgets because API and GPU costs scale roughly
  with chain count.

## Comparator policy and remaining scientific decisions

The comparator now maximizes `quality_challenge_utility`, the harmonic mean of
axis-conditioned teacher quality and matching target challenge. Aggregate validity
must remain at least `0.75`, quality at least `0.75`, and challenge at least `0.5`.
The harmonic mean prevents one strong component from masking a weak one, while the
floors fail closed before candidate ranking.

The remaining canary decision is whether these floors and the `0.01` meaningful
utility delta are calibrated to observed acceptance rates. Before a full run,
compare axis coverage, failure-mode coverage, duplicate rate, score distribution,
and downstream training value. A hard-example-only dataset may become narrow, so
production should retain explicit axis balance and monitor boundary cases rather
than assuming maximum difficulty alone is optimal.

One deterministic target answer is inexpensive but noisy. Multiple samples or a
failure-rate estimate can improve the challenge signal later, after measuring the
cost and disagreement rate in a single-response canary.

## Fast staged rollout

1. **Contract smoke test:** one prompt through Kimi, target Gemma, and Luna; verify
   identity checks, schema validation, rejection behavior, and metadata.
2. **Single-chain canary:** 32–64 rows with target probing; measure latency by stage,
   acceptance rate, failure-mode distribution, and cost per accepted row.
3. **Five-chain aggregate canary:** small equal budgets, per-chain concurrency 8,
   global limit 32, staggered starts, and no training. Verify fairness and recovery.
4. **One end-to-end candidate per chain:** generation, training, protected scoring,
   result publication, and parent advancement.
5. **Full Run 11:** enable normal budgets only after all five chains produce one
   durable score/result pair and no isolation or checkpoint-routing fault appears.

Capacity increases should use one variable at a time: global concurrency first,
then service replicas if queue and utilization measurements show a serving
bottleneck.

## Timing and observability requirements

For each chain and AAR iteration, retain timestamps and counts for:

- research/planning;
- AutoData bootstrap and baseline ingestion;
- each AutoData meta-optimization iteration;
- fixed-winner production generation;
- Kimi queue/inference, target Gemma queue/inference, and Luna queue/judging;
- validation, acceptance, deduplication, and replenishment;
- training queue and runtime;
- evaluator queue, checkpoint preparation, inference, and scoring; and
- result publication and parent-selection decisions.

Record p50/p95 latency, attempted/valid/accepted row counts, retries, 429/5xx rates,
tokens, GPU utilization, queue depth, and cost per accepted row. The primary speed
metric for data creation should be accepted target-challenging rows per wall-clock
minute, not raw request throughput.

## Related notes

- [Run 7 five-chain precedent](../run_7/README.md)
- [Run 9 implementation changes](../run_9/implementation_changes.md)
- [Run 9 AutoData nested-loop diagram](../run_9/autodata_nested_loops.svg)
