#!/usr/bin/env python3
"""Local-only Autodata HTTP contract smoke server.

This is orchestration test infrastructure, not a production data generator. It
emits a tiny deterministic arithmetic corpus and a real v1 manifest so an AAR
functional smoke can exercise generate/status/fetch and verified training loads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


def _canonical_rows(rows: list[dict]) -> str:
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)


class Handler(BaseHTTPRequestHandler):
    server_version = "AARAutodataContractSmoke/1"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        size = int(self.headers.get("Content-Length", "0"))
        value = json.loads(self.rfile.read(size) or b"{}")
        if not isinstance(value, dict):
            raise ValueError("request must be a JSON object")
        return value

    @property
    def state_root(self) -> Path:
        return self.server.state_root  # type: ignore[attr-defined]

    @property
    def pipeline_sha(self) -> str:
        return self.server.pipeline_sha  # type: ignore[attr-defined]

    def do_POST(self) -> None:  # noqa: N802
        try:
            if urlparse(self.path).path != "/v1/jobs":
                self._send(404, {"error": "not found"})
                return
            request = self._read_json()
            run_id = str(request.get("run_id", ""))
            spec = request.get("spec")
            if request.get("pipeline_sha") != self.pipeline_sha:
                raise ValueError("pipeline SHA mismatch")
            if not run_id or not isinstance(spec, dict):
                raise ValueError("run_id and spec are required")
            if spec.get("generator") != "programmatic_contract_smoke":
                raise ValueError(
                    "contract smoke requires AUTODATA_SPEC generator='programmatic_contract_smoke'"
                )
            run_dir = self.state_root / run_id
            request_bytes = json.dumps(request, sort_keys=True).encode()
            request_sha = hashlib.sha256(request_bytes).hexdigest()
            if (run_dir / "request.json").is_file():
                old = json.loads((run_dir / "request.json").read_text())
                if old.get("request_sha256") != request_sha:
                    raise ValueError("run_id already exists with a different request")
            else:
                run_dir.mkdir(parents=True, exist_ok=False)
                (run_dir / "request.json").write_text(
                    json.dumps({"request_sha256": request_sha, "request": request}, indent=2) + "\n"
                )
            rows = [
                {
                    "id": f"contract-{index:03d}",
                    "prompt": f"Return the integer immediately after {index}.",
                    "response": str(index + 1),
                    "provenance": {"generator": "programmatic_contract_smoke"},
                }
                for index in range(16)
            ]
            rows_payload = _canonical_rows(rows)
            manifest = {
                "schema": "aar.autodata.dataset/v1",
                "run_id": run_id,
                "pipeline_sha": self.pipeline_sha,
                "row_count": len(rows),
                "dataset_sha256": hashlib.sha256(rows_payload.encode()).hexdigest(),
                "generator": "programmatic_contract_smoke",
                "integration_smoke_only": True,
                "request_sha256": request_sha,
            }
            (run_dir / "artifacts.json").write_text(
                json.dumps({"rows": rows, "manifest": manifest}, indent=2) + "\n"
            )
            (run_dir / "status.json").write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "job_id": f"contract-{request_sha[:16]}",
                        "state": "complete",
                        "row_count": len(rows),
                        "integration_smoke_only": True,
                    },
                    indent=2,
                )
                + "\n"
            )
            self._send(200, json.loads((run_dir / "status.json").read_text()))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == "/health":
            self._send(200, {"status": "ok", "integration_smoke_only": True})
            return
        parts = [part for part in urlparse(self.path).path.split("/") if part]
        if len(parts) not in (3, 4) or parts[:2] != ["v1", "runs"]:
            self._send(404, {"error": "not found"})
            return
        run_dir = self.state_root / parts[2]
        path = run_dir / ("artifacts.json" if len(parts) == 4 and parts[3] == "artifacts" else "status.json")
        if not path.is_file():
            self._send(404, {"error": "run not found"})
            return
        self._send(200, json.loads(path.read_text()))

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[autodata-contract-smoke] {self.address_string()} {fmt % args}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--state-root", required=True)
    args = parser.parse_args()
    if os.getenv("AAR_AUTODATA_CONTRACT_SMOKE", "0") != "1":
        raise SystemExit("refusing to start without AAR_AUTODATA_CONTRACT_SMOKE=1")
    pipeline_sha = os.getenv("AAR_AUTODATA_SHA", "")
    if len(pipeline_sha) not in (40, 64):
        raise SystemExit("AAR_AUTODATA_SHA must be a full digest")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.state_root = Path(args.state_root).resolve()  # type: ignore[attr-defined]
    server.state_root.mkdir(parents=True, exist_ok=True)  # type: ignore[attr-defined]
    server.pipeline_sha = pipeline_sha  # type: ignore[attr-defined]
    print(f"[autodata-contract-smoke] listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
