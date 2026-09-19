#!/usr/bin/env bash
# Explicit hardware launcher; launching it starts the G1 standing initialization.
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
exec ./target/release/g1_deploy_onnx_ref "$sonic_interface" \
    policy/sonic_v1_1/model_decoder.onnx reference/example \
    --obs-config policy/sonic_v1_1/observation_config.yaml \
    --encoder-file policy/sonic_v1_1/model_encoder.onnx \
    --planner-file planner/target_vel/V2/planner_sonic.onnx \
    --hand-type "$sonic_hand_type" --input-type zmq_manager --output-type zmq \
    --motor-kp-scale 4,10=1.5 --motor-kd-scale 4,10=1.5 "$@"
