#!/usr/bin/env python3
"""Prune a terminal submission to its final PEFT adapter artifacts."""

from __future__ import annotations

import argparse
import json

from aar.transport import prune_terminal_adapter_submission


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--submission-dir", required=True)
    parser.add_argument("--terminal-marker", required=True)
    parser.add_argument("--retention", choices=("all",), default="all")
    args = parser.parse_args()
    result = prune_terminal_adapter_submission(
        args.submission_dir,
        args.terminal_marker,
        retention=args.retention,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
