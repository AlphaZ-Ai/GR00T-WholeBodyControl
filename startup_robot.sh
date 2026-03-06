#!/bin/bash
set -e

SESSION="robot"

# Kill existing session if it exists
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create new session with a single window
tmux new-session -d -s "$SESSION" -n "robot"

# Run motion switcher first, then control loop
tmux send-keys -t "$SESSION:robot" \
    "conda activate tv_ros && \
cd /home/unitree/AlphaZ_WS/xr_teleoperate && \
python teleop/utils/motion_switcher.py && \
source /opt/ros/humble/setup.bash && \
export ROS_DOMAIN_ID=0 && \
cd /home/unitree/AlphaZ_WS/GR00T-WholeBodyControl && \
python decoupled_wbc/control/main/teleop/run_g1_control_loop.py \
    --interface real --wbc_version gear_wbc --no_with_hands" Enter

# Attach to session
tmux attach-session -t "$SESSION"
