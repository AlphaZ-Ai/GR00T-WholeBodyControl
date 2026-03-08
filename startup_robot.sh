#!/bin/bash
set -e

SESSION="robot"

# Kill existing session if it exists
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create new session: window 0 = motion switcher (enter debug mode)
tmux new-session -d -s "$SESSION" -n "motion_switcher"

tmux send-keys -t "$SESSION:motion_switcher" \
    "conda activate tv_ros && \
cd /home/unitree/AlphaZ_WS/xr_teleoperate && \
python teleop/utils/motion_switcher.py" Enter

tmux new-window -t "$SESSION" -n "wbc"

tmux send-keys -t "$SESSION:wbc" \
    "sleep 3 && \
conda activate tv_ros && \
cd /home/unitree/AlphaZ_WS/GR00T-WholeBodyControl/gear_sonic_deploy && \
source scripts/setup_env.sh && \
([ -f target/release/g1_deploy_onnx_ref ] || just build) && \
./target/release/g1_deploy_onnx_ref enP8p1s0 \
    policy/release/model_decoder.onnx \
    reference/example/ \
    --obs-config policy/release/observation_config.yaml \
    --encoder-file policy/release/model_encoder.onnx \
    --planner-file planner/target_vel/V2/planner_sonic.onnx \
    --input-type zmq_manager \
    --output-type all" Enter

tmux attach-session -t "$SESSION:wbc"
