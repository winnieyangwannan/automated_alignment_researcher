from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Session numbers are one-based and span both the original attempt and the
# durable storage continuation. Sessions without a published score are absent.
CHAINS = {
    "alpha": {
        "color": "#0072B2",
        "sessions_started": 26,
        "points": [
            (2, 9.87, True),
            (3, 32.00, False),
            (14, 21.25, False),
            (15, 22.52, True),
            (18, 26.94, True),
            (19, 22.04, True),
            (21, 32.36, False),
            (23, 24.87, False),
            (25, 28.86, True),
        ],
    },
    "beta": {
        "color": "#D55E00",
        "sessions_started": 29,
        "points": [
            (1, 28.65, False),
            (3, 32.84, False),
            (4, 9.62, False),
            (5, 28.00, False),
            (7, 12.10, True),
            (8, 11.85, False),
            (9, 7.66, True),
            (10, 11.62, False),
            (11, 31.24, False),
            (12, 30.80, False),
            (14, 30.61, True),
            (15, 22.34, True),
            (19, 27.07, True),
            (20, 31.95, False),
            (21, 27.00, False),
            (23, 6.28, True),
            (24, 30.17, True),
            (25, 22.70, True),
            (26, 24.50, False),
            (27, 25.05, True),
            (28, 24.76, True),
        ],
    },
    "gamma": {
        "color": "#009E73",
        "sessions_started": 24,
        "points": [
            (1, 0.74, True),
            (2, 10.86, False),
            (3, 13.43, True),
            (4, 20.49, True),
            (7, 25.69, False),
            (8, 11.43, False),
            (9, 7.69, False),
            (10, 31.65, False),
            (11, 25.28, True),
            (12, 31.80, True),
            (14, 24.96, True),
            (15, 22.46, True),
            (16, 7.12, False),
        ],
    },
    "delta": {
        "color": "#CC79A7",
        "sessions_started": 24,
        "points": [
            (3, 6.95, True),
            (4, 19.75, True),
            (5, 26.28, False),
            (7, 29.58, False),
            (13, 16.29, False),
            (19, 20.75, False),
            (20, 22.85, True),
            (22, 28.05, True),
            (23, 14.71, True),
        ],
    },
    "epsilon": {
        "color": "#E69F00",
        "sessions_started": 28,
        "points": [
            (5, 19.31, True),
            (7, 21.25, False),
            (8, 15.55, True),
            (9, 28.49, True),
            (10, 29.99, False),
            (11, 30.97, True),
            (12, 28.83, False),
            (13, 30.15, False),
            (14, 27.98, True),
            (19, 24.18, False),
            (22, 18.35, True),
            (23, 20.41, False),
            (25, 12.27, True),
        ],
    },
}


def main() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(10, 6.18))
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    max_session = max(v["sessions_started"] for v in CHAINS.values())
    for chain, values in CHAINS.items():
        points = values["points"]
        sessions = [0, *[p[0] for p in points]]
        scores = [0.0, *[p[1] for p in points]]
        color = values["color"]
        ax.plot(
            sessions,
            scores,
            color=color,
            linewidth=2.0,
            marker="o",
            markersize=5.5,
            label=chain,
            zorder=3,
        )

    ax.axhline(0, color="#66737f", linewidth=1.2)
    ax.set_xlim(0, max_session + 0.5)
    ax.set_ylim(0, 35)
    ax.set_xticks([0, 5, 10, 15, 20, 25, max_session])
    ax.set_yticks(range(0, 36, 5))
    ax.set_xlabel("Research session", fontsize=11, fontweight="bold", labelpad=12)
    ax.set_ylabel("% of safety gap closed", fontsize=11, fontweight="bold", labelpad=8)

    fig.text(
        0.035,
        0.955,
        "AAR 5x30",
        ha="left",
        va="top",
        fontsize=18,
        fontweight="bold",
        color="#1f2933",
    )

    handles, labels = ax.get_legend_handles_labels()
    fig.legend(
        handles,
        labels,
        ncol=5,
        loc="upper center",
        bbox_to_anchor=(0.67, 0.902),
        frameon=False,
        fontsize=8,
        handlelength=2.1,
        columnspacing=1.5,
    )

    ax.text(0.35, 0.45, "retained baseline", fontsize=7, color="#66737f")
    fig.text(
        0.04,
        0.055,
        "●  published score",
        fontsize=8,
        color="#52606d",
    )
    ax.grid(axis="y", color="#dce1e5", linewidth=0.8)
    ax.grid(axis="x", visible=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#8a99a8")
    ax.tick_params(axis="both", labelsize=9, colors="#33404d")
    fig.subplots_adjust(left=0.055, right=0.94, bottom=0.15, top=0.83)

    output_png = Path(__file__).with_name("headline_closed_by_session_latest.png")
    output_svg = Path(__file__).with_name("headline_closed_by_session_latest.svg")
    fig.savefig(
        output_png, dpi=160, facecolor=fig.get_facecolor()
    )
    fig.savefig(output_svg, facecolor=fig.get_facecolor())
    print(output_png)
    print(output_svg)


if __name__ == "__main__":
    main()
