#!/bin/bash
set -euo pipefail
"${HARNESS_PY:-python}" - <<'PY'
import json
import os
import torch

print(json.dumps({
    "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
    "torch_cuda_available": torch.cuda.is_available(),
    "torch_cuda_device_count": torch.cuda.device_count(),
}))
if os.getenv("CUDA_VISIBLE_DEVICES") not in (None, "", "NoDevFiles"):
    raise SystemExit("CPU-only AAR unexpectedly has CUDA_VISIBLE_DEVICES")
if torch.cuda.is_available() or torch.cuda.device_count():
    raise SystemExit("CPU-only AAR unexpectedly has a visible CUDA device")
PY
