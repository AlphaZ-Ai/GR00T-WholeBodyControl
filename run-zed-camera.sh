#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export LD_LIBRARY_PATH="/usr/local/zed/lib:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
exec .venv_camera/bin/python -u -m gear_sonic.camera.composed_camera \
    --ego-view-camera zed --fps 30 --port 5555 "$@"
