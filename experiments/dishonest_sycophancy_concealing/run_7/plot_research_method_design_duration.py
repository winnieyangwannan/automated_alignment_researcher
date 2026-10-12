"""Plot Run 7 time from research-session start to method implementation.

The durable Run 7 continuation transcripts live on FAIR HPC.  This script
streams those logs over SSH, identifies the first mutation of a method package
in each session, and writes a per-session CSV plus PNG/SVG histograms.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import re
import shlex
import subprocess
import tarfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


DEFAULT_HOST = "fair-cw-use2-1"
DEFAULT_LOG_DIR = (
    "/storage/home/winnieyangwn/aar-recovery/run7_continuation_attempts/"
    "full_attempts/20261007T203258Z-a8fdf5b06629/aar_teams/"
    "honesty-sycophancy-concealing-gemma4_31b-opus48-"
    "run7-storage-continuation-1750282/logs"
)

START_RE = re.compile(r"^# Started: (\S+)", re.MULTILINE)
MESSAGE_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2})\] (?:AssistantMessage|UserMessage|SystemMessage|ResultMessage)\s*$",
    re.MULTILINE,
)
CHAIN_RE = re.compile(r"_explore_(alpha|beta|gamma|delta|epsilon)_")
METHOD_FILE_MUTATION_RE = re.compile(
    r"Tool: (?:Write|Edit).*?file_path.*?(?:/methods/|/aar/ideas/)",
    re.DOTALL,
)
METHOD_SHELL_MUTATION_RE = re.compile(
    r"Tool: Bash.*?(?:mkdir\s+-p|touch|cp\s+(?:-[A-Za-z]+\s+)?|cat\s+>|tee\s+)"
    r".*?(?:AAR_IDEAS_DIR|/methods/|/aar/ideas/)",
    re.DOTALL,
)


@dataclass(frozen=True)
class SessionTiming:
    session: str
    chain: str
    started_at: datetime
    implementation_started_at: datetime

    @property
    def duration_minutes(self) -> float:
        return (self.implementation_started_at - self.started_at).total_seconds() / 60


def fetch_logs(host: str, log_dir: str) -> dict[str, str]:
    remote_command = f"cd {shlex.quote(log_dir)} && tar -cf - session_*.log"
    result = subprocess.run(
        ["ssh", host, remote_command],
        check=True,
        stdout=subprocess.PIPE,
    )
    logs: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if member.isfile() and member.name.startswith("session_"):
                extracted = archive.extractfile(member)
                if extracted is not None:
                    logs[member.name] = extracted.read().decode("utf-8", errors="replace")
    return logs


def timestamp_on_or_after(started_at: datetime, clock: str) -> datetime:
    clock_time = datetime.strptime(clock, "%H:%M:%S").time()
    candidate = datetime.combine(started_at.date(), clock_time)
    if candidate < started_at - timedelta(minutes=1):
        candidate += timedelta(days=1)
    return candidate


def is_method_implementation(block: str) -> bool:
    return bool(
        METHOD_FILE_MUTATION_RE.search(block)
        or METHOD_SHELL_MUTATION_RE.search(block)
    )


def parse_session(name: str, text: str) -> SessionTiming | None:
    start_match = START_RE.search(text)
    chain_match = CHAIN_RE.search(name)
    if start_match is None or chain_match is None:
        return None

    started_at = datetime.fromisoformat(start_match.group(1))
    messages = list(MESSAGE_RE.finditer(text))
    for index, message in enumerate(messages):
        block_end = messages[index + 1].start() if index + 1 < len(messages) else len(text)
        block = text[message.start() : block_end]
        if not is_method_implementation(block):
            continue
        implementation_started_at = timestamp_on_or_after(started_at, message.group(1))
        duration = (implementation_started_at - started_at).total_seconds()
        if duration >= 0:
            return SessionTiming(
                session=name.removesuffix(".log"),
                chain=chain_match.group(1),
                started_at=started_at,
                implementation_started_at=implementation_started_at,
            )
    return None


def write_csv(path: Path, timings: list[SessionTiming]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "session",
                "chain",
                "started_at_utc",
                "implementation_started_at_utc",
                "research_method_design_minutes",
            ]
        )
        for timing in timings:
            writer.writerow(
                [
                    timing.session,
                    timing.chain,
                    timing.started_at.isoformat(),
                    timing.implementation_started_at.isoformat(),
                    f"{timing.duration_minutes:.3f}",
                ]
            )


def plot_histogram(
    output_dir: Path,
    timings: list[SessionTiming],
    total_sessions: int,
) -> None:
    values = np.array([timing.duration_minutes for timing in timings])
    median = float(np.median(values))
    mean = float(np.mean(values))
    p25, p75, p90 = np.percentile(values, [25, 75, 90])

    upper = max(10, int(math.ceil(values.max() / 5) * 5))
    bins = np.arange(0, upper + 5, 5)

    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(12.5, 7.2))
    fig.patch.set_facecolor("#fbfbfa")
    ax.set_facecolor("#fbfbfa")
    counts, _, patches = ax.hist(
        values,
        bins=bins,
        color="#4C78A8",
        edgecolor="white",
        linewidth=1.2,
    )
    for patch, left in zip(patches, bins[:-1]):
        if left <= median < left + 5:
            patch.set_facecolor("#2F5597")

    ax.axvline(median, color="#D55E00", linewidth=2.5, label=f"Median: {median:.1f} min")
    ax.axvline(
        mean,
        color="#009E73",
        linewidth=2.2,
        linestyle="--",
        label=f"Mean: {mean:.1f} min",
    )
    ax.set_title(
        "Run 7 research and method-design duration",
        loc="left",
        fontsize=20,
        fontweight="bold",
        pad=24,
    )
    ax.text(
        0,
        1.015,
        "Session start → first method-code mutation in durable continuation transcripts",
        transform=ax.transAxes,
        color="#52606d",
        fontsize=11,
    )
    ax.set_xlabel("Minutes before method implementation begins", fontsize=12, fontweight="bold")
    ax.set_ylabel("Research sessions", fontsize=12, fontweight="bold")
    ax.set_xticks(bins)
    ax.set_xlim(0, upper)
    ax.set_ylim(0, max(counts) * 1.18)
    ax.legend(frameon=True, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", visible=False)

    summary = (
        f"n={len(values)} of {total_sessions} sessions with observable implementation\n"
        f"IQR: {p25:.1f}–{p75:.1f} min  ·  p90: {p90:.1f} min"
    )
    ax.text(
        0.99,
        0.82,
        summary,
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10.5,
        color="#34495e",
        bbox={"boxstyle": "round,pad=0.5", "facecolor": "white", "edgecolor": "#d5d9dd"},
    )
    fig.tight_layout()

    stem = output_dir / "research_method_design_duration_histogram"
    fig.savefig(stem.with_suffix(".png"), dpi=200, bbox_inches="tight")
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)

    print(
        f"sessions={len(values)}/{total_sessions} "
        f"mean={mean:.3f} median={median:.3f} "
        f"p25={p25:.3f} p75={p75:.3f} p90={p90:.3f} "
        f"min={values.min():.3f} max={values.max():.3f}"
    )
    for chain in ("alpha", "beta", "gamma", "delta", "epsilon"):
        chain_values = np.array(
            [timing.duration_minutes for timing in timings if timing.chain == chain]
        )
        print(
            f"chain={chain} n={len(chain_values)} "
            f"median={np.median(chain_values):.3f} mean={np.mean(chain_values):.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--log-dir", default=DEFAULT_LOG_DIR)
    args = parser.parse_args()

    output_dir = Path(__file__).resolve().parent
    logs = fetch_logs(args.host, args.log_dir)
    timings = [
        timing
        for name, text in sorted(logs.items())
        if (timing := parse_session(name, text)) is not None
    ]
    if not timings:
        raise RuntimeError("No method-implementation boundaries found")

    write_csv(output_dir / "research_method_design_duration_by_session.csv", timings)
    plot_histogram(output_dir, timings, len(logs))


if __name__ == "__main__":
    main()
