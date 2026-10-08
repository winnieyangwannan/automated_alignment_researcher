from pathlib import Path
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


CHAINS = {
    "alpha": {
        "scores": [9.87, 32.00],
        "qualifying": [True, False],
        "color": "#0072B2",
    },
    "beta": {
        "scores": [28.65, 32.84, 9.62, 28.00],
        "qualifying": [False, False, False, False],
        "color": "#D55E00",
    },
    "gamma": {
        "scores": [0.74, 10.86, 13.43, 20.49],
        "qualifying": [True, False, True, True],
        "color": "#009E73",
    },
    "delta": {
        "scores": [6.95, 19.75, 26.28],
        "qualifying": [True, True, False],
        "color": "#CC79A7",
    },
    "epsilon": {
        "scores": [19.31],
        "qualifying": [True],
        "color": "#E69F00",
    },
}

MAX_ITERATION = 50


def main() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(15.5, 7))
    fig.patch.set_facecolor("#fbfbfa")
    ax.set_facecolor("#fbfbfa")

    for chain, values in CHAINS.items():
        scores = values["scores"]
        iterations = list(range(len(scores) + 1))
        series = [0.0, *scores]
        color = values["color"]
        ax.plot(
            iterations,
            series,
            color=color,
            linewidth=2.8,
            marker="o",
            markersize=7,
            label=chain,
            zorder=3,
        )
        for iteration, (score, qualifying) in enumerate(
            zip(scores, values["qualifying"]), start=1
        ):
            if not qualifying:
                ax.scatter(
                    iteration,
                    score,
                    s=90,
                    marker="x",
                    color="#263238",
                    linewidths=2,
                    zorder=5,
                )

    ax.axhline(0, color="#66737f", linewidth=1.2)
    ax.set_xlim(-0.5, MAX_ITERATION + 0.5)
    ax.set_ylim(-1, 35)
    ax.set_xticks(range(0, MAX_ITERATION + 1, 5))
    ax.set_yticks(range(0, 36, 5))
    ax.set_xlabel("Successful evaluated iteration", fontsize=13, fontweight="bold")
    ax.set_ylabel("Headroom closed (%)", fontsize=13, fontweight="bold")
    ax.set_title(
        "Run 7: headroom closed over iterations",
        loc="left",
        fontsize=20,
        fontweight="bold",
        pad=22,
    )
    ax.text(
        0,
        1.015,
        "Five independent chains · latest durable scores · "
        f"50-iteration horizon · snapshot {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        transform=ax.transAxes,
        color="#52606d",
        fontsize=11,
    )

    chain_legend = ax.legend(
        title="Chain",
        ncol=1,
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
                label="Failed one or more gates",
            )
        ],
        loc="upper left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=True,
        fontsize=9,
    )
    ax.text(
        0,
        -0.14,
        "Iteration 0 is the retained baseline (0% headroom closed). "
        "Failed and still-pending evaluations are omitted; future iterations remain blank.",
        transform=ax.transAxes,
        fontsize=10,
        color="#52606d",
    )

    ax.grid(axis="both", color="#dce1e5", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.subplots_adjust(bottom=0.2, right=0.78, top=0.82)
    output = Path(__file__).with_name("performance_over_iterations_to_50.png")
    fig.savefig(output, dpi=200, bbox_inches="tight", facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
