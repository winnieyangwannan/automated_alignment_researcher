#!/usr/bin/env python3
"""Plot the primary optimization method used by Run 7 candidate submissions."""

from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch


OUTPUT_DIR = Path(__file__).resolve().parent
SOURCE_CSV = OUTPUT_DIR / "data_generation_methods_coding.csv"
PNG_PATH = OUTPUT_DIR / "primary_training_methods_latest.png"
SVG_PATH = OUTPUT_DIR / "primary_training_methods_latest.svg"
CSV_PATH = OUTPUT_DIR / "primary_training_methods_coding.csv"
SNAPSHOT = "2026-10-08 07:10 UTC"

SFT = "Supervised fine-tuning (SFT)"
PREFERENCE = "Preference optimization (DPO / ORPO)"
SELF_DISTILL = "Self-distillation objective (forward KL)"
MERGING = "Model merging"
RL = "Reinforcement learning (RL)"

ORDER = (SFT, PREFERENCE, SELF_DISTILL, MERGING, RL)
COLORS = {
    SFT: "#71823b",
    PREFERENCE: "#15466a",
    SELF_DISTILL: "#f59d76",
    MERGING: "#2f6b5f",
    RL: "#d62728",
}

PREFERENCE_METHODS = {
    "faithful_calib_dpo",
    "faithful_report_dpo",
    "epsilon/apr_v1",
    "gamma/scpo_v1",
    "gamma/scpo_v2",
}
SELF_DISTILL_METHODS = {"anchored_belief_calib"}


def classify(method: str) -> tuple[str, str]:
    if method in PREFERENCE_METHODS:
        return PREFERENCE, "DPO/ORPO/odds-ratio preference objective in method source"
    if method in SELF_DISTILL_METHODS:
        return SELF_DISTILL, "forward-KL objective to the frozen base distribution"
    return SFT, "completion-only cross-entropy/NLL objective"


def whole_percentages(counts: Counter[str], total: int) -> dict[str, int]:
    """Largest-remainder rounding so displayed whole percentages sum to 100."""
    exact = {name: 100.0 * counts[name] / total for name in ORDER}
    rounded = {name: int(exact[name]) for name in ORDER}
    remaining = 100 - sum(rounded.values())
    ranked = sorted(ORDER, key=lambda name: exact[name] - rounded[name], reverse=True)
    for name in ranked[:remaining]:
        rounded[name] += 1
    return rounded


def main() -> None:
    rows: list[dict[str, str]] = []
    counts: Counter[str] = Counter()
    with SOURCE_CSV.open(encoding="utf-8", newline="") as handle:
        for source in csv.DictReader(handle):
            primary, evidence = classify(source["method"])
            attempts = int(source["candidate_submissions"])
            counts[primary] += attempts
            rows.append(
                {
                    "phase": source["phase"],
                    "method": source["method"],
                    "candidate_submissions": str(attempts),
                    "primary_training_method": primary,
                    "evidence": evidence,
                }
            )

    total = sum(counts.values())
    assert total == 81
    assert counts == Counter({SFT: 73, PREFERENCE: 6, SELF_DISTILL: 2})
    percentages = whole_percentages(counts, total)

    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": ["DejaVu Serif"],
            "text.color": "#050505",
        }
    )
    fig, ax = plt.subplots(figsize=(16, 6.2), dpi=180)
    fig.patch.set_facecolor("#fbfbfa")
    ax.set_facecolor("#fbfbfa")

    nonzero = [name for name in ORDER if counts[name] > 0]
    wedges, _ = ax.pie(
        [counts[name] for name in nonzero],
        colors=[COLORS[name] for name in nonzero],
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.40, "edgecolor": "#fbfbfa", "linewidth": 5},
    )

    for wedge, name in zip(wedges, nonzero):
        if percentages[name] < 5:
            continue
        angle = (wedge.theta1 + wedge.theta2) / 2
        radius = 0.80
        x = radius * math.cos(math.radians(angle))
        y = radius * math.sin(math.radians(angle))
        ax.text(
            x,
            y,
            f"{percentages[name]}%",
            ha="center",
            va="center",
            fontsize=24,
            fontweight="bold",
            color="white" if name in (SFT, PREFERENCE) else "black",
        )

    ax.text(0, 0, f"{total}\nsubmissions", ha="center", va="center", fontsize=25, fontweight="bold")
    ax.set_aspect("equal")
    ax.set_position((0.055, 0.08, 0.43, 0.84))

    fig.text(0.49, 0.78, "Primary training method", fontsize=25, ha="left", va="center")
    legend_handles = [Patch(facecolor=COLORS[name], edgecolor="#fbfbfa") for name in ORDER]
    legend_labels = [f"{name}  ({counts[name]}, {percentages[name]}%)" for name in ORDER]
    fig.legend(
        legend_handles,
        legend_labels,
        loc="center left",
        bbox_to_anchor=(0.485, 0.46),
        frameon=False,
        fontsize=18,
        handlelength=2.1,
        handletextpad=0.8,
        labelspacing=0.45,
    )
    fig.text(
        0.50,
        0.045,
        (
            "Primary objective, not data source · 34 original + 47 continuation candidates · "
            f"snapshot {SNAPSHOT}"
        ),
        ha="center",
        fontsize=11.5,
        color="#626b73",
    )

    fig.savefig(PNG_PATH, bbox_inches="tight", facecolor=fig.get_facecolor())
    fig.savefig(SVG_PATH, bbox_inches="tight", facecolor=fig.get_facecolor())

    for name in ORDER:
        print(f"{name}: {counts[name]}/{total} ({100 * counts[name] / total:.1f}%)")
    print(PNG_PATH)
    print(SVG_PATH)
    print(CSV_PATH)


if __name__ == "__main__":
    main()
