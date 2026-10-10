#!/bin/bash
#SBATCH --job-name=aar-run12-target-preflight
#SBATCH --account=ram
#SBATCH --partition=g3
#SBATCH --qos=g3_ram_high
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:10:00
set -euo pipefail
umask 077

REPO="${AAR_REPO:?submit through canary/canary_1/submit_target_canary.sh}"
ROOT="${AAR_RUN12_ROOT:?missing attempt root}"
BINDING="${AAR_RUN12_TARGET_BINDING:?missing target binding}"

start_ns="$(date +%s%N)"
PYTHONPATH="${REPO}" "${REPO}/.venv/bin/python" - "${BINDING}" "${ROOT}/preflight.json" "${start_ns}" <<'PY'
import json
import os
import pathlib
import sys
import tempfile
import time
import urllib.request

from aar.autodata_target_binding import load_binding

binding = load_binding(pathlib.Path(sys.argv[1]))
endpoint = binding.endpoint
headers = {"X-Deployment-Id": endpoint["deployment_id"]}
if endpoint.get("host_header"):
    headers["Host"] = endpoint["host_header"]

models_request = urllib.request.Request(endpoint["url"] + "/models", headers=headers)
request_start = time.monotonic()
with urllib.request.urlopen(models_request, timeout=30) as response:
    models = json.load(response)
model_ids = {
    item.get("id") for item in models.get("data", []) if isinstance(item, dict)
}
if endpoint["model"] not in model_ids:
    raise SystemExit("target model was absent from the selected deployment")

payload = {
    "model": endpoint["model"],
    "messages": [{"role": "user", "content": "Reply with exactly: RUN12_OK"}],
    "temperature": 0,
    "max_tokens": 16,
    "seed": 20261012,
}
generation_request = urllib.request.Request(
    endpoint["url"] + "/chat/completions",
    data=json.dumps(payload, sort_keys=True).encode(),
    headers={"Content-Type": "application/json", **headers},
    method="POST",
)
with urllib.request.urlopen(generation_request, timeout=90) as response:
    generation = json.load(response)
elapsed = time.monotonic() - request_start
request_id = generation.get("id")
usage = generation.get("usage")
choices = generation.get("choices")
if not isinstance(request_id, str) or not request_id:
    raise SystemExit("target response omitted request ID")
if not isinstance(usage, dict):
    raise SystemExit("target response omitted usage")
if not isinstance(choices, list) or not choices:
    raise SystemExit("target response omitted a completion")

report = {
    "schema": "aar.autodata.adapter-target-preflight/v1",
    "success": True,
    "target_iteration": binding.value["iteration"],
    "target_incumbent_run_id": binding.value["incumbent_run_id"],
    "target_checkpoint_hash": binding.checkpoint_hash,
    "target_model": endpoint["model"],
    "target_deployment_id": endpoint["deployment_id"],
    "request_id": request_id,
    "input_tokens": usage.get("prompt_tokens"),
    "output_tokens": usage.get("completion_tokens"),
    "endpoint_elapsed_seconds": round(elapsed, 3),
    "total_elapsed_seconds": round((time.time_ns() - int(sys.argv[3])) / 1e9, 3),
}
output = pathlib.Path(sys.argv[2])
descriptor, name = tempfile.mkstemp(prefix=".preflight.", suffix=".tmp", dir=output.parent)
temporary = pathlib.Path(name)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)
finally:
    temporary.unlink(missing_ok=True)
print(json.dumps(report, sort_keys=True))
PY

echo "Run 12 endpoint preflight passed: ${ROOT}/preflight.json"
