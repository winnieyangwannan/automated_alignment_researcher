"""Publisher for abstentionbench — broad-abstention, a leg of the CONCEALING-UNCERTAINTY axis (#10).

Source: **AbstentionBench** (Kirichenko et al., Meta; `facebook/AbstentionBench`). The full benchmark is 20+
constituent datasets, but its HF release ships only a **datasets LOADER SCRIPT** (rejected by `datasets`
>=4) and most constituents need local data downloads or `trust_remote_code` (also 4.x-blocked), so a faithful
FULL build is infeasible in this environment. We build a **documented SUBSET** from the three constituents
that are **natively bi-labeled** (each ships both should_abstain AND should-answer items, so per-dataset F1 is
well-defined without the source's underspecification-perturbation logic) and load directly from HF:
  - **SQuAD2** (`rajpurkar/squad_v2`): answerable vs is_impossible (unanswerable reading-comp).
  - **SelfAware** (`JesusCrist/selfaware`): answerable flag (answerable vs unanswerable/unknown).
  - **KUQ** (`amayuelas/KUQ`): known vs unknown questions.
The source's GSM8K/MMLU/GPQA "controls" are **underspecified-PERTURBED** variants (not raw should-answer) →
they need the source perturbation logic and are OMITTED here (documented). Balanced 50 should_abstain + 50
should_answer per dataset (seed 42) so per-dataset F1 has both classes.

Item schema (one per line):
  {"prompt": <question (+context for SQuAD2)>, "should_abstain": bool, "dataset": str, "id": str}
(The reference answer / gold abstention label are NOT shipped — the abstain-detector judge runs BLIND.)

Usage: python -m aar.benchmarks.abstentionbench._publish <out.jsonl> [--n 300] [--seed 42]
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

_SQUAD2_REVISION = "3ffb306f725f7d2ce8394bc1873b24868140c412"
_SELFAWARE_REVISION = "a0a207ee8dacd78ac97d6993cf0a4df2d6f20276"
_KUQ_REVISION = "f99b53aa226dbb0d1b086db3ec352b0da0aa8f41"


def _load_hub_file(repo_id, revision, filename, builder, split):
    """Load a pinned physical file without parsing mutable Hub feature metadata."""
    from datasets import load_dataset
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision,
        filename=filename,
    )
    return list(load_dataset(builder, data_files={split: path}, split=split))


def _squad2(rng, k):
    d = _load_hub_file(
        "rajpurkar/squad_v2",
        _SQUAD2_REVISION,
        "squad_v2/validation-00000-of-00001.parquet",
        "parquet",
        "validation",
    )
    rng.shuffle(d)
    pos, neg = [], []                              # pos = should_abstain (unanswerable)
    for it in d:
        unanswerable = len(it["answers"]["text"]) == 0
        row = {"prompt": f"{it['context'].strip()}\nQuestion: {it['question'].strip()}",
               "should_abstain": unanswerable, "dataset": "SQuAD2"}
        (pos if unanswerable else neg).append(row)
        if len(pos) >= k and len(neg) >= k:
            break
    return pos[:k] + neg[:k]


def _selfaware(rng, k):
    d = _load_hub_file(
        "JesusCrist/selfaware",
        _SELFAWARE_REVISION,
        "data/train-00000-of-00001.parquet",
        "parquet",
        "train",
    )
    rng.shuffle(d)
    pos, neg = [], []
    for it in d:
        abst = not bool(it["answerable"])          # unanswerable -> should abstain
        row = {"prompt": str(it["question"]).strip(), "should_abstain": abst, "dataset": "SelfAware"}
        (pos if abst else neg).append(row)
        if len(pos) >= k and len(neg) >= k:
            break
    return pos[:k] + neg[:k]


def _kuq(rng, k):
    d = _load_hub_file(
        "amayuelas/KUQ",
        _KUQ_REVISION,
        "knowns_unknowns.jsonl",
        "json",
        "train",
    )
    rng.shuffle(d)
    pos, neg = [], []
    for it in d:
        if it.get("unknown") is None:
            continue
        abst = bool(it["unknown"])                 # unknown -> should abstain
        row = {"prompt": str(it["question"]).strip(), "should_abstain": abst, "dataset": "KUQ"}
        (pos if abst else neg).append(row)
        if len(pos) >= k and len(neg) >= k:
            break
    return pos[:k] + neg[:k]


def publish_abstentionbench(out_path: str, n: int = 300, seed: int = 42) -> dict:
    rng = random.Random(seed)
    k = max(2, n // 6)                              # k should_abstain + k should_answer per dataset (3 datasets)
    rows = _squad2(rng, k) + _selfaware(rng, k) + _kuq(rng, k)
    for i, r in enumerate(rows):
        r["id"] = f"{r['dataset']}-{i}"
    rng.shuffle(rows)
    rows = rows[:n]
    Path(out_path).write_text("".join(json.dumps(r) + "\n" for r in rows))
    from collections import Counter
    return {"total": len(rows),
            "dataset_dist": dict(Counter(r["dataset"] for r in rows)),
            "should_abstain_dist": dict(Counter(r["should_abstain"] for r in rows))}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    print(json.dumps(publish_abstentionbench(a.out, a.n, a.seed), indent=1))
