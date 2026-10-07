#!/usr/bin/env python3
"""Run one real OCI task through the native AutoData Firecracker broker."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tempfile
import time
import uuid
from pathlib import Path


DEFAULT_IMAGE = (
    "docker.io/library/python@sha256:"
    "05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f"
)
DEFAULT_IMAGE_ID = "df18428df8a0f9189c84e7424d214b4c50092af1f9dca5842a00c41c39bda316"
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker-url", default="http://127.0.0.1:8791")
    parser.add_argument("--broker-auth-token-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    from autodata.broker.archive import build_archive, extract_archive, file_identity
    from autodata.broker.client import BrokerClient
    from autodata.broker.models import BrokerJobSpec

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autodata-native-canary-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        workspace.mkdir()
        (workspace / "solve.py").write_text(
            "from pathlib import Path\n"
            "import json\n"
            "Path('output').mkdir(exist_ok=True)\n"
            "Path('output/result.json').write_text(json.dumps({'ok': True}) + '\\n')\n",
            encoding="utf-8",
        )
        archive = root / "workspace.tar.gz"
        build_archive(workspace, archive)
        identity = file_identity(archive)
        key = f"run8-native-canary:{uuid.uuid4().hex}"
        spec = BrokerJobSpec.from_dict(
            {
                "schema": "autodata.broker-job/v1",
                "idempotency_key": key,
                "task": "write a deterministic native broker canary result",
                "environment": "oci-runner-firecracker-small",
                "image": DEFAULT_IMAGE,
                "expected_image_id": DEFAULT_IMAGE_ID,
                "workspace": {
                    "sha256": identity.sha256,
                    "size_bytes": identity.size,
                },
                "solve": {
                    "argv": ["python3", "solve.py"],
                    "timeout_seconds": 120,
                    "network": "none",
                    "result_paths": ["output/result.json"],
                },
                "model_backed": False,
                "lease_duration_seconds": 900,
                "max_output_bytes": 1 << 20,
            }
        )
        auth_token = None
        if args.broker_auth_token_file is not None:
            token_path = args.broker_auth_token_file.resolve(strict=True)
            info = token_path.lstat()
            if (
                stat.S_ISLNK(info.st_mode)
                or not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
            ):
                raise RuntimeError(
                    "broker auth token file must be an owned mode-0600 regular file"
                )
            auth_token = token_path.read_text().strip()
            if not auth_token or any(character.isspace() for character in auth_token):
                raise RuntimeError("broker auth token file must contain one token")
        client = BrokerClient(args.broker_url, auth_token)
        created = client.json_request("POST", "/v1/jobs", spec.to_dict())
        job_id = str(created["id"])
        client.upload(job_id, "workspace", archive)
        deadline = time.monotonic() + args.timeout_seconds
        status = created
        while time.monotonic() < deadline:
            status = client.json_request("GET", f"/v1/jobs/{job_id}")
            if status.get("status") in TERMINAL:
                break
            time.sleep(2)
        else:
            raise TimeoutError(f"native broker canary did not finish: {job_id}")
        if status.get("status") != "SUCCEEDED":
            raise RuntimeError(
                f"native broker canary failed: {job_id}: {status.get('error')}"
            )
        result_archive = root / "results.tar.gz"
        client.download_results(job_id, result_archive)
        extracted = root / "result"
        extract_archive(result_archive, extracted)
        result = json.loads((extracted / "output" / "result.json").read_text())
        if result != {"ok": True}:
            raise RuntimeError("native broker canary returned an unexpected result")
        report = {
            "schema": "aar.autodata.native-broker-canary/v1",
            "success": True,
            "broker_job_id": job_id,
            "broker_status": status.get("status"),
            "sandoq_session_id": status.get("session_id"),
            "environment": spec.environment,
            "image": spec.image,
            "expected_image_id": spec.expected_image_id,
        }
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
