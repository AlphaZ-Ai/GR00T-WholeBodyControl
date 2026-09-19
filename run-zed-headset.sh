#!/usr/bin/env bash
# ZED Mini for BOTH the PICO headset (stereo pass-through) and SONIC (ego_view on :5555).
#
# Replaces run-zed-camera.sh whenever the headset should see through the robot: the ZED
# SDK allows one owner, so XRoboToolkit's OrinVideoSender owns the camera (it answers the
# headset app's open-camera command on 13579 and streams H.264 to it on 12345) and
# zed_sender_to_sonic.py republishes the left eye in SONIC's camera format on 5555.
# Stop run-zed-camera.sh first; do not run both.
#
#   ./run-zed-headset.sh
#
# Then in the headset's XRoboToolkit app: camera type ZED, this Thor's IP (10.0.2.87),
# command port 13579, stream port 12345, open the camera. The ZED opens on that request
# (HD720, 60 fps), so nothing streams until the headset asks.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
SENDER=external_dependencies/XRoboToolkit-Orin-Video-Sender/OrinVideoSender
[[ -x $SENDER ]] || { echo "build the sender first: (cd external_dependencies/XRoboToolkit-Orin-Video-Sender && make)" >&2; exit 1; }
if ss -ltn 2>/dev/null | grep -q ":5555 "; then
    echo "port 5555 is already served (run-zed-camera.sh or another zed_sender_to_sonic.py); stop it first" >&2; exit 1
fi
export LD_LIBRARY_PATH="/usr/local/zed/lib:/usr/local/cuda/lib64:${LD_LIBRARY_PATH:-}"
"$SENDER" --listen 0.0.0.0:13579 --zmq-raw tcp://*:5601 &
SENDER_PID=$!
trap 'kill $SENDER_PID 2>/dev/null || true' EXIT INT TERM
sleep 2
exec .venv_camera/bin/python zed_sender_to_sonic.py --raw-endpoint tcp://127.0.0.1:5601 --port 5555 "$@"
