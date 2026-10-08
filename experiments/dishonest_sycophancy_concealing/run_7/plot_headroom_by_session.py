from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


SNAPSHOT_UTC = "2026-10-08 08:18 UTC"

# Session numbers are one-based and span both the original attempt and the
# durable storage continuation. Sessions without a published score are absent.
CHAINS = {
    "alpha": {
        "color": "#0072B2",
        "sessions_started": 16,
        "points": [
            (2, 9.87, True),
            (3, 32.00, False),
            (14, 21.25, False),
            (15, 22.52, True),
        ],
    },
    "beta": {
        "color": "#D55E00",
        "sessions_started": 19,
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
        ],
    },
    "gamma": {
        "color": "#009E73",
        "sessions_started": 17,
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
        "sessions_started": 16,
        "points": [
            (3, 6.95, True),
            (4, 19.75, True),
            (5, 26.28, False),
            (7, 29.58, False),
            (13, 16.29, False),
        ],
    },
    "epsilon": {
        "color": "#E69F00",
        "sessions_started": 18,
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
        ],
    },
}


def main() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(15.5, 8.2))
    fig.patch.set_facecolor("#fbfbfa")
    ax.set_facecolor("#fbfbfa")

    max_session = max(v["sessions_started"] for v in CHAINS.values())
    for chain, values in CHAINS.items():
        points = values["points"]
        sessions = [p[0] for p in points]
        scores = [p[1] for p in points]
        color = values["color"]
        ax.plot(
            sessions,
            scores,
            color=color,
            linewidth=2.6,
            marker="o",
            markersize=7,
            label=chain,
            zorder=3,
        )
        for session, score, valid in points:
            if not valid:
                ax.scatter(
                    session,
                    score,
                    s=95,
                    marker="x",
                    color="#263238",
                    linewidths=2.2,
                    zorder=5,
                )

        # A small triangle shows how far the chain has progressed even when
        # its newest session has not yet produced a score.
        ax.scatter(
            values["sessions_started"],
            -1.15,
            marker="^",
            s=55,
            color=color,
            edgecolor="white",
            linewidth=0.7,
            zorder=4,
        )

    ax.axhline(0, color="#66737f", linewidth=1.2)
    ax.set_xlim(0.5, max_session + 0.5)
    ax.set_ylim(-2.2, 35)
    ax.set_xticks(range(1, max_session + 1))
    ax.set_yticks(range(0, 36, 5))
    ax.set_xlabel("Research session number", fontsize=13, fontweight="bold")
    ax.set_ylabel("Headroom closed (%)", fontsize=13, fontweight="bold")
    ax.set_title(
        "Run 7: headroom closed by research session",
        loc="left",
        fontsize=21,
        fontweight="bold",
        pad=24,
    )
    ax.text(
        0,
        1.015,
        "Five independent chains · original attempt + durable continuation · "
        f"snapshot {SNAPSHOT_UTC}",
        transform=ax.transAxes,
        color="#52606d",
        fontsize=11,
    )

    chain_legend = ax.legend(
        title="Chain",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        frameon=True,
    )
    ax.add_artist(chain_legend)
    ax.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="x",
                linestyle="none",
                color="#263238",
                markersize=8,
                markeredgewidth=2,
                label="Evaluated, but failed a gate",
            ),
            Line2D(
                [0],
                [0],
                marker="^",
                linestyle="none",
                color="#66737f",
                markersize=7,
                label="Latest session started",
            ),
        ],
        loc="upper left",
        bbox_to_anchor=(1.01, 0.56),
        frameon=True,
        fontsize=9,
    )

    ax.text(
        0,
        -0.14,
        "Lines connect sessions with completed evaluations. Blank session positions had no published score or are still pending; "
        "triangles show each chain's latest started session.",
        transform=ax.transAxes,
        fontsize=10,
        color="#52606d",
    )

    ax.grid(axis="both", color="#dce1e5", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.subplots_adjust(bottom=0.20, right=0.76, top=0.83)

    output = Path(__file__).with_name("headroom_by_session_latest.png")
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(output)


if __name__ == "__main__":
    main()
