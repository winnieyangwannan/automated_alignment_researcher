# Run 12 canaries

The two Run 12 gates are separated by purpose and pass criterion:

```text
canary_1/
  one AutoData task: Kimi → Gemma → Luna
  verifies routing, identity, provenance, and broker execution

canary_2/
  one AAR chain: meta-optimization → 1,000 accepted production rows
  verifies the handoff with one real GPU optimizer step, then stops
```

- [`canary_1/`](canary_1/README.md) is the lightweight infrastructure gate. It
  has passed.
- [`canary_2/`](canary_2/README.md) is the production data-to-training gate. It
  has not passed yet.

Only after both gates pass should the five-chain, five-iteration run launch.

## Model and execution roles

Canary 2 deliberately exercises several independent roles. “Judge” is
ambiguous here: proposal approval, training-row judgment, and held-out
evaluation are different operations.

```text
AAR control plane
├─ AAR researcher
│  └─ Kimi-K2.6, deployment aar_8-kimi26
│     Direct Serve API v2 proxy behind a credential-hiding local bridge
├─ AAR proposal and AutoData-approval monitor
│  └─ claude-4-8-opus through Meta Model API
│     Reviews method policy/reproducibility/leakage and signs only native
│     AutoData approval actions whose evidence passes review
├─ AAR training model
│  └─ Gemma 4 31B IT fixed base + a new PEFT adapter
│     Runs locally in the one-step GPU training job; it is not an API
└─ AAR evaluator and evaluation judge
   └─ Not launched in Canary 2; there is no held-out score

AutoData data plane
├─ AutoData generator (the row-authoring model)
│  └─ Kimi-K2.6, dedicated deployment autodata_8-kimi26
│     Selected through ram-inference-gateway by exact deployment ID and
│     exposed to Local Bubblewrap tasks through an authenticated bridge
├─ AutoData target probe
│  └─ Chain-specific Gemma 4 31B IT deployment
│     Canary 2 uses the fixed base; later full-run iterations use the fixed
│     base plus that chain's previously promoted adapter
├─ AutoData row judge
│  └─ gpt-5-6-luna through Meta Model API Responses
│     Scores teacher quality and whether the Gemma target materially fails
├─ AutoData orchestrator and broker
│  └─ Trusted CPU code plus Local Bubblewrap, not model endpoints
│     Own lifecycle state, concurrency, retries, isolation, and provenance
└─ AutoData comparator
   └─ Deterministic code, not another LLM
      Compares valid quality and target challenge across strategies
```

The deployment IDs are stable logical identities; physical proxy addresses are
discovered and health-checked at runtime rather than permanently hard-coded.
Credentials remain in trusted host bridges and are not exposed to generated
tasks. Canary 1 tests one complete Kimi → Gemma → Luna task. Canary 2 adds
the AAR researcher, approvals, three meta-iterations, full production volume,
verified dataset consumption, and one optimizer step.

`legacy_submit_research_canary.sh` is retained only for historical
reproducibility. It launched a scored Kimi research iteration during early
adapter-attachment work and is not a third operational gate.
