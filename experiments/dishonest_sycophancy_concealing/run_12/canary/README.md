# Run 12 canaries

The two Run 12 gates are separated by purpose and pass criterion:

```text
canary_1/
  one AutoData task: Kimi → Gemma → Luna
  verifies routing, identity, provenance, and broker execution

canary_2/
  one AAR chain: meta-optimization → 100 accepted production rows
  verifies production generation and stops before training/evaluation
```

- [`canary_1/`](canary_1/README.md) is the lightweight infrastructure gate. It
  has passed.
- [`canary_2/`](canary_2/README.md) is the production data-generation gate. It
  has not passed yet.

Only after both gates pass should the five-chain, five-iteration run launch.

`legacy_submit_research_canary.sh` is retained only for historical
reproducibility. It launched a scored Kimi research iteration during early
adapter-attachment work and is not a third operational gate.
