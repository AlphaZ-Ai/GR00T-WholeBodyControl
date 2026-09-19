#!/usr/bin/env bash
set -e
source "$(dirname "${BASH_SOURCE[0]}")/sonic-env.sh"
cd "$SONIC_ROOT"
exec .venv_sim/bin/python -u gear_sonic/scripts/run_sim_loop.py --interface sim "$@"
