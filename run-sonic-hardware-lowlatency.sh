#!/usr/bin/env bash
# SONIC LOW-LATENCY teleoperation checkpoint on the physical G1 (4-frame / ~80 ms reference
# lookahead instead of v1.1's 10-frame / ~200 ms): the responsive choice for VR teleop and
# data collection. Same safety notes as run-sonic-hardware.sh: launching starts the
# standing initialisation; robot supported, e-stop in reach.
#
#   ./run-sonic-hardware-lowlatency.sh enP2p1s0 dex1 --dex1-swap-sides
#
# No ankle gain scales: the 4,10=1.5 Kp/Kd tuning is the tested v1.1 setting and NVIDIA
# documents it as checkpoint-specific. Add --motor-kp-scale/--motor-kd-scale explicitly
# if the low-latency model turns out to need them on this robot. The first start compiles
# the TensorRT engines for the new ONNX files (a few minutes); they are cached beside them.
set -euo pipefail
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <robot-network-interface> <dex1-internal|dex1> [controller options]" >&2
    exit 2
fi
sonic_interface="$1"
sonic_hand_type="$2"
shift 2
case "$sonic_hand_type" in dex1|dex1-internal) ;; *) echo "Select dex1-internal or dex1" >&2; exit 2;; esac
if [[ "$sonic_interface" == lo || ! -d "/sys/class/net/$sonic_interface" ]]; then
    echo "Specify the physical robot network interface" >&2
    exit 2
fi
if [[ "$(cat "/sys/class/net/$sonic_interface/operstate")" != up ]]; then
    echo "Robot interface $sonic_interface is down; connect the robot first" >&2
    exit 1
fi
source "$(dirname "${BASH_SOURCE[0]}")/sonic-env.sh"
cd "$SONIC_ROOT/gear_sonic_deploy"
[[ -f policy/low_latency/model_decoder.onnx ]] || { echo "low-latency checkpoint missing: .venv_models/bin/python download_from_hf.py --low-latency" >&2; exit 1; }
exec ./target/release/g1_deploy_onnx_ref "$sonic_interface" \
    policy/low_latency/model_decoder.onnx reference/example \
    --obs-config policy/low_latency/observation_config.yaml \
    --encoder-file policy/low_latency/model_encoder.onnx \
    --planner-file planner/target_vel/V2/planner_sonic.onnx \
    --hand-type "$sonic_hand_type" --input-type zmq_manager --output-type zmq "$@"
