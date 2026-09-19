#!/usr/bin/env bash
# XRoboToolkit PC service (the PICO headset connects to it) on this Thor, headless.
# The bundled arm64 build links ICU 70 (Ubuntu 22.04); this Thor runs 24.04 with ICU 74,
# so the 22.04 ICU libraries live in ~/opt/icu70 (extracted from libicu70_70.1-2_arm64.deb).
# Start BEFORE the PICO app tries to connect; the headset enters this machine's IP
# (Tailscale: 100.96.139.69).
set -euo pipefail
DIR=/opt/apps/roboticsservice
export LD_LIBRARY_PATH="$HOME/opt/icu70:$DIR:$DIR/lib:$DIR/SDK/arm64:${LD_LIBRARY_PATH:-}"
export QT_PLUGIN_PATH="$DIR/plugins/"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
cd "$DIR"
exec ./RoboticsServiceProcess "$@"
