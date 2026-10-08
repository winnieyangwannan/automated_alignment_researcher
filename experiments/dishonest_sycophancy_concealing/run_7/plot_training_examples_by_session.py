#!/usr/bin/env python3
"""Plot Run 7 final training-record counts by research session.

Counts are the post-filter records passed to training.  An SFT example counts
as one record and a preference pair counts as one record.  Repeated candidate
submissions are retained.  Seven original-attempt counts could not be
recovered after the checkpoint NFS namespace disappeared; they are shown as
unavailable rather than estimated.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


SNAPSHOT = "2026-10-08 07:10 UTC"
OUTPUT_DIR = Path(__file__).resolve().parent
PNG_PATH = OUTPUT_DIR / "training_examples_by_session_latest.png"
SVG_PATH = OUTPUT_DIR / "training_examples_by_session_latest.svg"
CSV_PATH = OUTPUT_DIR / "training_examples_by_session.csv"

CHAIN_COLORS = {
    "alpha": "#0072B2",
    "beta": "#D55E00",
    "gamma": "#009E73",
    "delta": "#CC79A7",
    "epsilon": "#E69F00",
}
ORIGINAL_SESSIONS = {"alpha": 7, "beta": 6, "gamma": 5, "delta": 6, "epsilon": 6}


@dataclass(frozen=True)
class Candidate:
    phase: str
    chain: str
    session: int
    method: str
    training_records: int | None
    evidence: str


def original(chain: str, session: int, method: str, count: int | None) -> Candidate:
    evidence = "recovered original training log/session summary" if count is not None else "unavailable after NFS loss"
    return Candidate("original", chain, session, method, count, evidence)


def continuation(chain: str, local_session: int, method: str, count: int) -> Candidate:
    session = ORIGINAL_SESSIONS[chain] + local_session + 1
    return Candidate("continuation", chain, session, method, count, "durable train job log")


CANDIDATES = (
    # Original checkpoint-backed attempt. Multiple rows at one session are
    # genuine retraining/resubmission attempts and are plotted separately.
    original("alpha", 1, "belief_calib_distill", 300),
    original("alpha", 1, "belief_calib_distill", 300),
    original("alpha", 2, "belief_calib_distill", 300),
    original("alpha", 3, "calib_belief_distill", 346),
    original("alpha", 4, "anchored_belief_calib", None),
    original("alpha", 5, "anchored_belief_calib", None),
    original("alpha", 6, "bdpa_v1", 410),
    original("alpha", 7, "bdpa_v2", None),
    original("beta", 1, "cdhc_v1", 116),
    original("beta", 1, "cdhc_v1", 523),
    original("beta", 2, "ktcc_v1", 660),
    original("beta", 3, "cshc_v1", 643),
    original("beta", 4, "bdrd_v1", None),
    original("beta", 5, "swap_v1", 501),
    original("beta", 6, "dcc_v1", 501),
    original("gamma", 1, "isca_v1", 333),
    original("gamma", 1, "isca_v1", 333),
    original("gamma", 2, "scgc_v1", None),
    original("gamma", 3, "coac_v1", None),
    original("gamma", 4, "chac_v1", 548),
    original("gamma", 5, "ntha_v1", 640),
    original("delta", 1, "skcfr_sft", 285),
    original("delta", 1, "skcfr_sft", 285),
    original("delta", 2, "fsr_selfconf", 64),
    original("delta", 3, "caspr_v1", 283),
    original("delta", 4, "mdna_v1", 409),
    original("delta", 5, "pdas_v1", 500),
    original("delta", 6, "skca_v1", 580),
    original("epsilon", 1, "faithful_report_dpo", 141),
    original("epsilon", 2, "faithful_report_dpo", 107),
    original("epsilon", 3, "faithful_calib_dpo", None),
    original("epsilon", 4, "faithful_report_sft", 125),
    original("epsilon", 5, "faithful_report_sft", 135),
    original("epsilon", 6, "faithful_anchor_sft", 181),
    # Durable continuation: exact final record counts from train job logs.
    continuation("alpha", 0, "scec_v1", 294),
    continuation("alpha", 1, "scec_v2", 242),
    continuation("alpha", 2, "egca_v1", 241),
    continuation("alpha", 3, "egca_v2", 201),
    continuation("alpha", 4, "egca_v3", 241),
    continuation("alpha", 5, "egca_v3", 245),
    continuation("alpha", 6, "gcsa_v1", 326),
    continuation("alpha", 7, "gcsa_v2", 335),
    continuation("beta", 0, "cuesc_v1", 286),
    continuation("beta", 1, "cvc_v1", 326),
    continuation("beta", 2, "dmca_v1", 335),
    continuation("beta", 3, "dmca_v2", 497),
    continuation("beta", 4, "dpsr_v1", 227),
    continuation("beta", 5, "ptsr_v1", 230),
    continuation("beta", 6, "ffh_v1", 246),
    continuation("beta", 7, "clbh_v1", 309),
    continuation("beta", 8, "fbh_v1", 270),
    continuation("beta", 9, "fbh_v1", 272),
    continuation("gamma", 0, "bhsa_v1", 404),
    continuation("gamma", 1, "fiba_v1", 174),
    continuation("gamma", 2, "dcap_v1", 342),
    continuation("gamma", 3, "cgpr_v1", 411),
    continuation("gamma", 4, "xsca_v1", 250),
    continuation("gamma", 5, "decsa_v1", 260),
    continuation("gamma", 6, "smca_v1", 274),
    continuation("gamma", 7, "smca_v2", 311),
    continuation("gamma", 8, "smca_v3", 298),
    continuation("gamma", 9, "scpo_v1", 288),
    continuation("gamma", 10, "scpo_v2", 284),
    continuation("delta", 0, "ckc_v1", 415),
    continuation("delta", 1, "dmcc_v1", 446),
    continuation("delta", 2, "dmcc_v2", 363),
    continuation("delta", 3, "scvc_v1", 300),
    continuation("delta", 4, "gscc_v1", 279),
    continuation("delta", 5, "dvca_v1", 220),
    continuation("delta", 6, "dcvc_v1", 296),
    continuation("delta", 7, "gvca_v1", 247),
    continuation("epsilon", 0, "faithful_anchor_sft", 178),
    continuation("epsilon", 1, "ntca_v1", 190),
    continuation("epsilon", 2, "csca_v1", 206),
    continuation("epsilon", 3, "cjc_v1", 298),
    continuation("epsilon", 4, "scm_v1", 234),
    continuation("epsilon", 5, "cfc_v1", 223),
    continuation("epsilon", 6, "apr_v1", 208),
    continuation("epsilon", 7, "scgc_v1", 271),
    continuation("epsilon", 8, "dvca_v1", 288),
    continuation("epsilon", 9, "dvca_v2", 272),
)


def write_manifest() -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("phase", "chain", "research_session", "attempt_in_session", "method", "training_records", "evidence"))
        attempts: Counter[tuple[str, int]] = Counter()
        for item in CANDIDATES:
            attempts[(item.chain, item.session)] += 1
            writer.writerow(
                (
                    item.phase,
                    item.chain,
                    item.session,
                    attempts[(item.chain, item.session)],
                    item.method,
                    "" if item.training_records is None else item.training_records,
                    item.evidence,
                )
            )


def main() -> None:
    assert len(CANDIDATES) == 81
    assert sum(item.phase == "original" for item in CANDIDATES) == 34
    assert sum(item.phase == "continuation" for item in CANDIDATES) == 47
    known = [item.training_records for item in CANDIDATES if item.training_records is not None]
    missing = len(CANDIDATES) - len(known)
    known_total = sum(known)
    write_manifest()

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["DejaVu Serif"],
            "axes.edgecolor": "#202020",
            "axes.labelcolor": "#202020",
            "xtick.color": "#202020",
            "ytick.color": "#202020",
        }
    )
    chains = tuple(CHAIN_COLORS)
    fig, axes = plt.subplots(len(chains), 1, figsize=(17, 12.5), dpi=180, sharex=True, sharey=True)
    fig.patch.set_facecolor("#fbfbfa")

    for ax, chain in zip(axes, chains):
        ax.set_facecolor("#fbfbfa")
        rows = [item for item in CANDIDATES if item.chain == chain]
        per_session = Counter(item.session for item in rows)
        seen = Counter()
        for item in rows:
            seen[item.session] += 1
            n_at_session = per_session[item.session]
            offset = 0.0 if n_at_session == 1 else (seen[item.session] - (n_at_session + 1) / 2) * 0.5
            x = item.session + offset
            if item.training_records is None:
                ax.scatter(x, 25, marker="x", s=75, linewidths=2.2, color="#687078", zorder=5)
                ax.text(x, 52, "?", ha="center", va="bottom", fontsize=9, color="#687078", fontweight="bold")
            else:
                ax.vlines(x, 0, item.training_records, color=CHAIN_COLORS[chain], alpha=0.24, linewidth=2)
                ax.scatter(
                    x,
                    item.training_records,
                    s=62,
                    color=CHAIN_COLORS[chain],
                    edgecolor="white",
                    linewidth=0.8,
                    zorder=4,
                )
                ax.text(
                    x,
                    item.training_records + 17,
                    f"{item.training_records}",
                    ha="center",
                    va="bottom",
                    fontsize=7.7,
                    color="#2f3437",
                )

        boundary = ORIGINAL_SESSIONS[chain] + 0.5
        ax.axvspan(0.5, boundary, color="#eceff1", alpha=0.6, zorder=0)
        ax.axvline(boundary, color="#77818a", linestyle=(0, (4, 4)), linewidth=1.1)
        ax.text(0.012, 0.82, chain, transform=ax.transAxes, fontsize=13, fontweight="bold", color=CHAIN_COLORS[chain])
        ax.set_ylim(0, 720)
        ax.set_yticks((0, 200, 400, 600))
        ax.grid(axis="y", color="#dce1e5", linewidth=0.8)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0, labelsize=10)

    max_session = max(item.session for item in CANDIDATES)
    axes[-1].set_xlim(0.5, max_session + 0.5)
    axes[-1].set_xticks(range(1, max_session + 1))
    axes[-1].set_xlabel("Research session number within each chain (original + continuation)", fontsize=13, labelpad=10)
    fig.supylabel("Final training records", fontsize=14, x=0.055)
    fig.suptitle(
        "Run 7 training-set size by research session",
        x=0.09,
        y=0.975,
        ha="left",
        fontsize=23,
        fontstyle="italic",
        color="#72787d",
    )
    fig.text(
        0.09,
        0.943,
        "Shaded = original NFS-backed attempt · dashed line = durable-continuation boundary · repeated submissions are offset",
        ha="left",
        fontsize=11.5,
        color="#52606d",
    )
    fig.text(
        0.5,
        0.018,
        (
            f"N=81 submitted candidates (34 original + 47 continuation), snapshot {SNAPSHOT}. "
            f"Known lower bound: {known_total:,} records across {len(known)} candidates; "
            f"{missing} original counts unavailable after NFS loss (×/?). Preference pairs count as one record."
        ),
        ha="center",
        fontsize=10.5,
        color="#626b73",
    )
    fig.subplots_adjust(left=0.09, right=0.975, top=0.91, bottom=0.09, hspace=0.12)
    fig.savefig(PNG_PATH, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(SVG_PATH, bbox_inches="tight", facecolor=fig.get_facecolor())

    print(f"known_candidates={len(known)} missing_candidates={missing} known_total={known_total}")
    print(PNG_PATH)
    print(SVG_PATH)
    print(CSV_PATH)


if __name__ == "__main__":
    main()
