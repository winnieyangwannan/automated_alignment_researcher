from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

from plot_headroom_by_session import CHAINS


CORAL = "#df7d5f"
DOT_GRAY = "#c4c2b9"
INK = "#282822"
MUTED = "#77776f"
OUTER = "#ffffff"
PANEL = "#ffffff"
MAX_SESSION = 30


def main() -> None:
    scored = [
        (session, score, valid)
        for values in CHAINS.values()
        for session, score, valid in values["points"]
    ]
    valid_scores = [(session, score) for session, score, valid in scored if valid]

    best_by_session = []
    best = 0.0
    for session in range(MAX_SESSION + 1):
        scores_at_session = [
            score for scored_session, score in valid_scores if scored_session == session
        ]
        if scores_at_session:
            best = max(best, max(scores_at_session))
        best_by_session.append(best)

    best_score = max(best_by_session)
    best_session = next(
        session for session, score in enumerate(best_by_session) if score == best_score
    )

    fig = plt.figure(figsize=(10, 6.18), facecolor=OUTER)
    panel = FancyBboxPatch(
        (0.012, 0.045),
        0.976,
        0.84,
        boxstyle="round,pad=0.012,rounding_size=0.035",
        transform=fig.transFigure,
        facecolor=PANEL,
        edgecolor="none",
        zorder=-10,
    )
    fig.patches.append(panel)
    ax = fig.add_axes([0.085, 0.16, 0.84, 0.64], facecolor=PANEL)

    ax.scatter(
        [session for session, _, _ in scored],
        [score for _, score, _ in scored],
        s=24,
        color=DOT_GRAY,
        edgecolor=PANEL,
        linewidth=0.7,
        alpha=0.95,
        zorder=2,
    )
    ax.step(
        range(MAX_SESSION + 1),
        best_by_session,
        where="post",
        color=CORAL,
        linewidth=2.4,
        zorder=4,
    )
    ax.scatter(
        best_session,
        best_score,
        marker="*",
        s=190,
        color=CORAL,
        edgecolor=PANEL,
        linewidth=1.0,
        zorder=5,
    )
    ax.annotate(
        f"{best_score:.1f}%",
        (best_session, best_score),
        xytext=(-10, 11),
        textcoords="offset points",
        ha="right",
        color=CORAL,
        fontsize=12,
        fontweight="bold",
    )

    ax.annotate(
        "",
        xy=(0.022, 0.985),
        xytext=(0.022, 0.86),
        xycoords="axes fraction",
        arrowprops={"arrowstyle": "-|>", "color": MUTED, "linewidth": 1.2},
    )
    ax.text(
        0.037,
        0.945,
        "Safer",
        transform=ax.transAxes,
        color=MUTED,
        fontsize=9,
        va="center",
    )

    ax.set_xlim(0, MAX_SESSION + 1)
    ax.set_ylim(0, 100)
    ax.set_xticks([0, 6, 12, 18, 24, 30])
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Research session", fontsize=11, color=MUTED)
    ax.set_ylabel("% of safety gap closed", fontsize=11, color=MUTED)
    ax.tick_params(axis="both", labelsize=9, colors=MUTED)
    ax.grid(False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#8e8e87")

    fig.text(
        0.5,
        0.96,
        "AAR 5x30",
        ha="center",
        va="top",
        fontsize=23,
        fontweight="bold",
        color=INK,
    )
    legend_handles = [
        Line2D([0], [0], color=CORAL, linewidth=2.4, label="Best method so far"),
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="none",
            markerfacecolor=DOT_GRAY,
            markeredgecolor="none",
            markersize=6,
            label="Each method tried",
        ),
    ]
    ax.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.52, 1.0),
        ncol=2,
        frameon=True,
        fancybox=True,
        framealpha=1,
        facecolor=PANEL,
        edgecolor="#96968e",
        fontsize=9,
        handlelength=1.8,
        columnspacing=1.7,
    )

    output_png = Path(__file__).with_name("aar_5x30_frontier_style.png")
    output_svg = Path(__file__).with_name("aar_5x30_frontier_style.svg")
    fig.savefig(output_png, dpi=160, facecolor=fig.get_facecolor())
    fig.savefig(output_svg, facecolor=fig.get_facecolor())
    print(output_png)
    print(output_svg)


if __name__ == "__main__":
    main()
