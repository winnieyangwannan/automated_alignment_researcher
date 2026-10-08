#!/usr/bin/env python3
"""Plot a manually audited, multi-label coding of Run 7 data generation methods.

The observation unit is a candidate submission, not a successful evaluation.  The
snapshot combines 34 submissions recovered from the original NFS-backed attempt
and 47 submissions from the durable continuation as of 2026-10-08 07:10 UTC.
Repeated submissions are retained because the requested view is across research
sessions/attempts rather than across unique method names.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt


SNAPSHOT = "2026-10-08 07:10 UTC"
OUTPUT_DIR = Path(__file__).resolve().parent
PNG_PATH = OUTPUT_DIR / "data_generation_methods_latest.png"
SVG_PATH = OUTPUT_DIR / "data_generation_methods_latest.svg"
CSV_PATH = OUTPUT_DIR / "data_generation_methods_coding.csv"

SELF = "Target-model self-generation / context distillation"
PROGRAM = "Programmatic / templated prompt construction"
PRESSURE = "Hard-negative / adversarial pressure variants"
CONTROL = "Matched / two-sided controls"
ANCHOR = "Mode-matched anchor / replay"
VERIFY = "Verifier / gating filters"
CONFIDENCE = "Self-consistency / confidence labels"
PREFERENCE = "Preference-pair generation"

CATEGORIES = (
    PROGRAM,
    SELF,
    PRESSURE,
    CONTROL,
    ANCHOR,
    VERIFY,
    CONFIDENCE,
    PREFERENCE,
)


@dataclass(frozen=True)
class Coding:
    phase: str
    method: str
    attempts: int
    categories: frozenset[str]
    evidence: str


BASE = frozenset({SELF, PROGRAM, PRESSURE})
CONTINUATION_BASE = BASE | {CONTROL, ANCHOR, VERIFY}


def row(
    phase: str,
    method: str,
    attempts: int = 1,
    *,
    add: tuple[str, ...] = (),
    drop: tuple[str, ...] = (),
    evidence: str,
) -> Coding:
    categories = (CONTINUATION_BASE if phase == "continuation" else BASE) | set(add)
    categories -= set(drop)
    return Coding(phase, method, attempts, frozenset(categories), evidence)


CODING = (
    # Original NFS-backed attempt: recovered method source where available, plus
    # proposal/finding text in the salvaged Claude session logs.
    row("original", "anchored_belief_calib", 2, add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py"),
    row("original", "bdpa_v1", add=(CONTROL, ANCHOR), evidence="salvaged run.py"),
    row("original", "bdpa_v2", add=(CONTROL, ANCHOR), evidence="salvaged session/proposal"),
    row("original", "belief_calib_distill", 3, add=(CONTROL, ANCHOR, VERIFY), evidence="salvaged run.py + finding"),
    row("original", "calib_belief_distill", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "bdrd_v1", add=(CONTROL, ANCHOR, VERIFY), evidence="salvaged run.py + finding"),
    row("original", "cdhc_v1", 2, add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "cshc_v1", add=(CONTROL, ANCHOR, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "dcc_v1", add=(CONTROL, ANCHOR, CONFIDENCE), evidence="salvaged run.py"),
    row("original", "ktcc_v1", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py"),
    row("original", "swap_v1", add=(ANCHOR,), evidence="recovered finding"),
    row("original", "caspr_v1", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "fsr_selfconf", add=(CONFIDENCE,), evidence="salvaged run.py"),
    row("original", "mdna_v1", add=(CONTROL, ANCHOR), evidence="salvaged run.py + finding"),
    row("original", "pdas_v1", add=(CONTROL, ANCHOR), evidence="salvaged run.py + finding"),
    row("original", "skca_v1", add=(CONTROL, ANCHOR, VERIFY), evidence="salvaged run.py"),
    row("original", "skcfr_sft", 2, add=(CONFIDENCE,), evidence="salvaged run.py"),
    row("original", "faithful_anchor_sft", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py"),
    row("original", "faithful_calib_dpo", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE, PREFERENCE), evidence="salvaged run.py"),
    row("original", "faithful_report_dpo", 2, add=(CONTROL, ANCHOR, VERIFY, PREFERENCE), evidence="salvaged run.py"),
    row("original", "faithful_report_sft", 2, add=(CONTROL, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "chac_v1", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "coac_v1", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "isca_v1", 2, add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),
    row("original", "ntha_v1", add=(CONTROL, ANCHOR, CONFIDENCE), evidence="salvaged run.py"),
    row("original", "scgc_v1", add=(CONTROL, ANCHOR, VERIFY, CONFIDENCE), evidence="salvaged run.py + finding"),

    # Durable continuation: coding is based on each submitted method's run.py.
    row("continuation", "alpha/egca_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "alpha/egca_v2", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "alpha/egca_v3", 2, add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "alpha/gcsa_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "alpha/gcsa_v2", evidence="run.py"),
    row("continuation", "alpha/scec_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "alpha/scec_v2", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "beta/clbh_v1", evidence="run.py"),
    row("continuation", "beta/cuesc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "beta/cvc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "beta/dmca_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "beta/dmca_v2", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "beta/dpsr_v1", evidence="run.py"),
    row("continuation", "beta/fbh_v1", 2, evidence="run.py"),
    row("continuation", "beta/ffh_v1", evidence="run.py"),
    row("continuation", "beta/ptsr_v1", evidence="run.py"),
    row("continuation", "delta/ckc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "delta/dcvc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "delta/dmcc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "delta/dmcc_v2", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "delta/dvca_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "delta/gscc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "delta/gvca_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "delta/scvc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "epsilon/apr_v1", add=(PREFERENCE,), evidence="run.py"),
    row("continuation", "epsilon/cfc_v1", evidence="run.py"),
    row("continuation", "epsilon/cjc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "epsilon/csca_v1", evidence="run.py"),
    row("continuation", "epsilon/dvca_v1", evidence="run.py"),
    row("continuation", "epsilon/dvca_v2", evidence="run.py"),
    row("continuation", "epsilon/faithful_anchor_sft", evidence="run.py"),
    row("continuation", "epsilon/ntca_v1", evidence="run.py"),
    row("continuation", "epsilon/scgc_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "epsilon/scm_v1", evidence="run.py"),
    row("continuation", "gamma/bhsa_v1", evidence="run.py"),
    row("continuation", "gamma/cgpr_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "gamma/dcap_v1", add=(CONFIDENCE,), evidence="run.py"),
    row("continuation", "gamma/decsa_v1", evidence="run.py"),
    row("continuation", "gamma/fiba_v1", evidence="run.py"),
    row("continuation", "gamma/scpo_v1", add=(PREFERENCE,), evidence="run.py"),
    row("continuation", "gamma/scpo_v2", add=(PREFERENCE,), evidence="run.py"),
    row("continuation", "gamma/smca_v1", evidence="run.py"),
    row("continuation", "gamma/smca_v2", evidence="run.py"),
    row("continuation", "gamma/smca_v3", evidence="run.py"),
    row("continuation", "gamma/xsca_v1", evidence="run.py"),
)


def write_manifest() -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("phase", "method", "candidate_submissions", *CATEGORIES, "evidence"))
        for item in CODING:
            writer.writerow(
                (
                    item.phase,
                    item.method,
                    item.attempts,
                    *("1" if category in item.categories else "0" for category in CATEGORIES),
                    item.evidence,
                )
            )


def main() -> None:
    total = sum(item.attempts for item in CODING)
    original = sum(item.attempts for item in CODING if item.phase == "original")
    continuation = sum(item.attempts for item in CODING if item.phase == "continuation")
    assert (total, original, continuation) == (81, 34, 47)

    counts = {
        category: sum(item.attempts for item in CODING if category in item.categories)
        for category in CATEGORIES
    }
    ordered = sorted(CATEGORIES, key=lambda category: (-counts[category], CATEGORIES.index(category)))
    percentages = [100.0 * counts[category] / total for category in ordered]

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
    fig, ax = plt.subplots(figsize=(17, 9.2), dpi=180)
    fig.patch.set_facecolor("#fbfbfa")
    ax.set_facecolor("#fbfbfa")

    y_positions = range(len(ordered))
    bars = ax.barh(y_positions, percentages, color="#929292", height=0.68)
    ax.set_yticks(list(y_positions), ordered, fontsize=17)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xticks((0, 25, 50, 75, 100))
    ax.tick_params(axis="x", labelsize=16, width=1.5, length=8)
    ax.tick_params(axis="y", width=1.5, length=7)
    ax.xaxis.grid(True, color="#dde1e4", linewidth=1.0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_linewidth(1.6)

    for bar, category, percentage in zip(bars, ordered, percentages):
        inside = percentage >= 90
        ax.text(
            percentage - 1.2 if inside else percentage + 1.1,
            bar.get_y() + bar.get_height() / 2,
            f"{percentage:.0f}%",
            va="center",
            ha="right" if inside else "left",
            fontsize=18,
            fontweight="bold",
            color="#0c0c0c",
        )

    ax.set_title(
        "How Run 7 constructs / filters training data (multi-label)",
        fontsize=23,
        fontstyle="italic",
        color="#8a8a8a",
        loc="left",
        pad=20,
    )
    ax.set_xlabel("Share of candidate submissions using each mechanism (%)", fontsize=17, labelpad=10)
    fig.text(
        0.5,
        0.025,
        (
            f"N={total} submitted candidates ({original} original + {continuation} continuation); "
            f"manual coding from method source/proposals; snapshot {SNAPSHOT}. Percentages overlap."
        ),
        ha="center",
        fontsize=11.5,
        color="#626b73",
    )
    fig.subplots_adjust(left=0.42, right=0.965, top=0.88, bottom=0.15)
    fig.savefig(PNG_PATH, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(SVG_PATH, bbox_inches="tight", facecolor=fig.get_facecolor())

    for category in ordered:
        print(f"{category}: {counts[category]}/{total} ({100 * counts[category] / total:.1f}%)")
    print(PNG_PATH)
    print(SVG_PATH)
    print(CSV_PATH)


if __name__ == "__main__":
    main()
