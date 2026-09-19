#!/usr/bin/env bash
# SONIC V1.1 controller for the local MuJoCo simulator (loopback only).
set -e
source "$(dirname "${BASH_SOURCE[0]}")/sonic-env.sh"
cd "$SONIC_ROOT/gear_sonic_deploy"
exec ./target/release/g1_deploy_onnx_ref lo \
    policy/sonic_v1_1/model_decoder.onnx reference/example \
    --obs-config policy/sonic_v1_1/observation_config.yaml \
    --encoder-file policy/sonic_v1_1/model_encoder.onnx \
    --planner-file planner/target_vel/V2/planner_sonic.onnx \
    --input-type keyboard --output-type zmq --disable-crc-check \
    --motor-kp-scale 4,10=1.5 --motor-kd-scale 4,10=1.5 "$@"
