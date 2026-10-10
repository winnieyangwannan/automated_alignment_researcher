#!/usr/bin/env python3
"""Render a Run-7-style frontier directly from an AAR attempt's artifacts."""

from __future__ import annotations

import argparse
import bisect
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SESSION_RE = re.compile(
    r"^session_\d+_.+?_explore_(?P<chain>[A-Za-z0-9]+)_"
    r"(?P<started>\d{8}_\d{6})\.log$"
)
RUN_CREATED_RE = re.compile(r"-(?P<created_ms>\d{13})$")


@dataclass(frozen=True)
class FrontierPoint:
    chain: str
    session: int
    score: float
    valid: bool
    run_id: str


def resolve_team_dir(path: Path) -> tuple[Path, Path | None]:
    """Return (team_dir, attempt_dir) from either accepted input layout."""
    path = path.expanduser().resolve(strict=True)
    if (path / "scores").is_dir() and (path / "logs").is_dir():
        attempt = path.parent.parent if path.parent.name == "aar_teams" else None
        return path, attempt
    teams_root = path / "aar_teams"
    teams = sorted(candidate for candidate in teams_root.glob("*") if candidate.is_dir())
    if len(teams) != 1:
        raise ValueError(f"expected exactly one team under {teams_root}, found {len(teams)}")
    return teams[0], path


def _session_starts(team_dir: Path) -> dict[str, list[datetime]]:
    starts: dict[str, set[datetime]] = {}
    for path in (team_dir / "logs").glob("session_*.log"):
        match = SESSION_RE.match(path.name)
        if match is None:
            continue
        started = datetime.strptime(
            match.group("started"), "%Y%m%d_%H%M%S"
        ).replace(tzinfo=timezone.utc)
        starts.setdefault(match.group("chain"), set()).add(started)
    return {chain: sorted(values) for chain, values in starts.items()}


def _score_chain(run_id: str, chains: list[str]) -> str | None:
    matches = [chain for chain in chains if f"-explore-{chain}-" in run_id]
    return matches[0] if len(matches) == 1 else None


def load_frontier_points(team_dir: Path) -> tuple[list[FrontierPoint], dict[str, int]]:
    """Join score filenames to chronological per-chain research sessions."""
    starts = _session_starts(team_dir)
    points: list[FrontierPoint] = []
    for path in sorted((team_dir / "scores").glob("*.json")):
        if path.name.endswith(".failed.json"):
            continue
        run_id = path.stem
        chain = _score_chain(run_id, sorted(starts))
        created_match = RUN_CREATED_RE.search(run_id)
        if chain is None or created_match is None:
            continue
        payload: dict[str, Any] = json.loads(path.read_text())
        score = payload.get("headline_pct")
        if not isinstance(score, (int, float)):
            continue
        created = datetime.fromtimestamp(
            int(created_match.group("created_ms")) / 1000, tz=timezone.utc
        )
        session = bisect.bisect_right(starts[chain], created)
        if session == 0:
            continue
        points.append(
            FrontierPoint(
                chain=chain,
                session=session,
                score=float(score),
                valid=bool(payload.get("passes_filter"))
                and bool(payload.get("passes_regression")),
                run_id=run_id,
            )
        )
    points.sort(key=lambda point: (point.session, point.chain, point.run_id))
    return points, {chain: len(values) for chain, values in starts.items()}


def _recorded_max_sessions(attempt_dir: Path | None) -> int | None:
    if attempt_dir is None:
        return None
    children = attempt_dir / "metadata" / "children.env"
    if not children.is_file():
        return None
    for line in children.read_text().splitlines():
        if line.startswith("max_iterations_per_chain="):
            value = line.partition("=")[2]
            return int(value) if value.isdigit() else None
    return None


def render_frontier(
    points: list[FrontierPoint],
    *,
    output_stem: Path,
    max_session: int,
    title: str,
    subtitle: str,
) -> tuple[Path, Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import FancyBboxPatch

    coral = "#df7d5f"
    dot_gray = "#c4c2b9"
    ink = "#282822"
    muted = "#77776f"
    outer = "#ffffff"
    panel_color = "#ffffff"

    valid_points = [point for point in points if point.valid]
    best_by_session: list[float] = []
    best = 0.0
    for session in range(max_session + 1):
        candidates = [
            point.score for point in valid_points if point.session == session
        ]
        if candidates:
            best = max(best, max(candidates))
        best_by_session.append(best)

    fig = plt.figure(figsize=(10, 6.18), facecolor=outer)
    panel = FancyBboxPatch(
        (0.012, 0.045),
        0.976,
        0.84,
        boxstyle="round,pad=0.012,rounding_size=0.035",
        transform=fig.transFigure,
        facecolor=panel_color,
        edgecolor="none",
        zorder=-10,
    )
    fig.patches.append(panel)
    ax = fig.add_axes([0.085, 0.16, 0.84, 0.64], facecolor=panel_color)

    ax.scatter(
        [point.session for point in points],
        [point.score for point in points],
        s=24,
        color=dot_gray,
        edgecolor=panel_color,
        linewidth=0.7,
        alpha=0.95,
        zorder=2,
    )
    ax.step(
        range(max_session + 1),
        best_by_session,
        where="post",
        color=coral,
        linewidth=2.4,
        zorder=4,
    )
    if valid_points:
        best_score = max(point.score for point in valid_points)
        best_session = min(
            point.session for point in valid_points if point.score == best_score
        )
        ax.scatter(
            best_session,
            best_score,
            marker="*",
            s=190,
            color=coral,
            edgecolor=panel_color,
            linewidth=1.0,
            zorder=5,
        )
        ax.annotate(
            f"{best_score:.1f}%",
            (best_session, best_score),
            xytext=(-10, 11),
            textcoords="offset points",
            ha="right",
            color=coral,
            fontsize=12,
            fontweight="bold",
        )

    ax.annotate(
        "",
        xy=(0.022, 0.985),
        xytext=(0.022, 0.86),
        xycoords="axes fraction",
        arrowprops={"arrowstyle": "-|>", "color": muted, "linewidth": 1.2},
    )
    ax.text(
        0.037,
        0.945,
        "Safer",
        transform=ax.transAxes,
        color=muted,
        fontsize=9,
        va="center",
    )
    tick_step = max(1, max_session // 5)
    x_ticks = list(range(0, max_session + 1, tick_step))
    if x_ticks[-1] != max_session:
        x_ticks.append(max_session)
    ax.set_xlim(0, max_session + 1)
    ax.set_ylim(0, 100)
    ax.set_xticks(x_ticks)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Research session", fontsize=11, color=muted)
    ax.set_ylabel("% of safety gap closed", fontsize=11, color=muted)
    ax.tick_params(axis="both", labelsize=9, colors=muted)
    ax.grid(False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#8e8e87")

    fig.text(
        0.5,
        0.96,
        title,
        ha="center",
        va="top",
        fontsize=23,
        fontweight="bold",
        color=ink,
    )
    if subtitle:
        fig.text(0.5, 0.905, subtitle, ha="center", va="top", fontsize=9, color=muted)
    ax.legend(
        handles=[
            Line2D([0], [0], color=coral, linewidth=2.4, label="Best valid method so far"),
            Line2D(
                [0],
                [0],
                marker="o",
                linestyle="none",
                markerfacecolor=dot_gray,
                markeredgecolor="none",
                markersize=6,
                label="Each evaluated method",
            ),
        ],
        loc="upper center",
        bbox_to_anchor=(0.52, 1.0),
        ncol=2,
        frameon=True,
        fancybox=True,
        framealpha=1,
        facecolor=panel_color,
        edgecolor="#96968e",
        fontsize=9,
        handlelength=1.8,
        columnspacing=1.7,
    )

    output_stem.parent.mkdir(parents=True, exist_ok=True)
    png_path = output_stem.with_suffix(".png")
    svg_path = output_stem.with_suffix(".svg")
    fig.savefig(png_path, dpi=160, facecolor=fig.get_facecolor())
    fig.savefig(svg_path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return png_path, svg_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="AAR attempt or team directory")
    parser.add_argument("--output-stem", type=Path, required=True)
    parser.add_argument("--max-session", type=int)
    parser.add_argument("--title")
    parser.add_argument("--subtitle", default="")
    args = parser.parse_args()

    team_dir, attempt_dir = resolve_team_dir(args.path)
    points, sessions_started = load_frontier_points(team_dir)
    if not points:
        raise SystemExit(f"no scored methods could be joined to sessions in {team_dir}")
    max_session = args.max_session or _recorded_max_sessions(attempt_dir) or max(
        sessions_started.values()
    )
    if max_session < max(point.session for point in points):
        raise SystemExit("max session is smaller than an observed scored session")
    title = args.title or f"AAR {len(sessions_started)}×{max_session}"
    snapshot = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    subtitle = args.subtitle or (
        f"{len(points)} evaluated methods · {sum(point.valid for point in points)} valid · "
        f"snapshot {snapshot.replace('+00:00', 'Z')}"
    )
    png_path, svg_path = render_frontier(
        points,
        output_stem=args.output_stem,
        max_session=max_session,
        title=title,
        subtitle=subtitle,
    )
    summary_path = args.output_stem.with_suffix(".json")
    summary_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshot_utc": snapshot,
                "team_dir": str(team_dir),
                "max_session": max_session,
                "sessions_started": sessions_started,
                "points": [asdict(point) for point in points],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(png_path)
    print(svg_path)
    print(summary_path)


if __name__ == "__main__":
    main()
