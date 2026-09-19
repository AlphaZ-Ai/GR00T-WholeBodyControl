#!/usr/bin/env bash
# Isaac-GR00T PolicyServer ON THE THOR for a fine-tuned N1.7 checkpoint (UNITREE_G1_SONIC).
#
#   ./run-gr00t-server.sh <checkpoint dir or HF model id> [--port 5550] [other run_gr00t_server.py args]
#   ./run-gr00t-server.sh ~/checkpoints/g1_press_sonic/checkpoint-20000
#
# Uses ~/alphaz_ws/Isaac-GR00T at the Jetson AI Lab validated commit 9c7e746 with its Thor
# (CUDA 13.0, Python 3.12) dependency set in .venv (torch 2.10 cu130, flash-attn 2.8.4 from
# pypi.jetson-ai-lab.io). Measured on this Thor with the 3B base model: ~6.2 GB GPU memory,
# ~175 ms per 40-step action chunk in PyTorch (the client asks at 2.5 Hz, so this is fine).
# NVPL BLAS/LAPACK for the aarch64 torch wheel is extracted under ~/opt/nvpl (no sudo needed).
set -euo pipefail
GR00T="${GR00T_ROOT:-$HOME/alphaz_ws/Isaac-GR00T}"
[[ $# -ge 1 ]] || { echo "usage: $0 <checkpoint dir or HF id> [--port 5550] [args]" >&2; exit 2; }
CKPT="$1"; shift
[[ -x "$GR00T/.venv/bin/python" ]] || { echo "no $GR00T/.venv (see VLA_INFERENCE_THOR.md)" >&2; exit 1; }
cd "$GR00T"
source .venv/bin/activate
source scripts/activate_thor.sh >/dev/null
export LD_LIBRARY_PATH="$HOME/opt/nvpl/usr/lib/aarch64-linux-gnu:${LD_LIBRARY_PATH:-}"
export NO_ALBUMENTATIONS_UPDATE=1
exec python -u gr00t/eval/run_gr00t_server.py --model-path "$CKPT" --embodiment-tag UNITREE_G1_SONIC \
    --device cuda:0 --port 5550 "$@"
