#!/usr/bin/env bash
# Robot-side VLA inference client for a fine-tuned GR00T N1.7 (UNITREE_G1_SONIC) policy.
#
# The PolicyServer runs on a GPU machine (Isaac-GR00T, port 5550); this client runs on the
# Thor next to the C++ controller: it reads the ego_view camera (:5555) and robot state
# (:5557), asks the server for 40-step action chunks at 2.5 Hz and publishes SONIC latent
# actions + hand joints to the controller (:5556). Keys are typed into keyboard_publisher.py.
#
#   ./run-vla-inference.sh <policy-host> ["prompt"] [extra run_vla_inference.py args]
#   ./run-vla-inference.sh 100.x.y.z                      # Tailscale IP of the GPU box
#
# Bring-up order (each in its own terminal):
#   1. GPU box:  uv run python gr00t/eval/run_gr00t_server.py --model-path <ckpt> \
#                    --embodiment-tag UNITREE_G1_SONIC --port 5550
#   2. Thor:     ./run-sonic-hardware-lowlatency.sh enP2p1s0 dex1 --dex1-swap-sides
#                (the SAME SONIC checkpoint the demos were recorded with)
#   3. Thor:     ./run-zed-camera.sh   (or ./run-zed-headset.sh)   -> ego_view on :5555
#   4. Thor:     ./run-vla-inference.sh <policy-host>
#   5. Thor:     .venv_inference/bin/python keyboard_publisher.py   then type: k, i, ] (if the
#                gripper should start closed), p.   p again pauses, k stops the controller.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
HOST="${1:-localhost}"; shift || true
PROMPT="${1:-press the light switch}"; [[ $# -gt 0 ]] && shift
[[ -x .venv_inference/bin/python ]] || { echo ".venv_inference missing (see VLA_INFERENCE_THOR.md)" >&2; exit 1; }
if ! ss -ltn 2>/dev/null | grep -q ":5557 "; then
    echo "warning: no controller state on :5557 yet (start run-sonic-hardware-lowlatency.sh first)" >&2
fi
exec .venv_inference/bin/python -u gear_sonic/scripts/run_vla_inference.py \
    --host "$HOST" --port 5550 --prompt "$PROMPT" --camera-host localhost --camera-port 5555 "$@"
