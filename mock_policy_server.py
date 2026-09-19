#!/usr/bin/env python3
"""Replay PolicyServer: serves a recorded SONIC episode's action chunks over the
Isaac-GR00T PolicyServer protocol, so the whole robot-side inference chain
(camera -> run_vla_inference.py -> C++ deploy) can be exercised without a GPU or
a trained checkpoint. Each get_action returns the next 40-step chunk of
motion_token / left_hand_joints / right_hand_joints from the episode, and prints
what the observation looked like on the first request (keys and shapes) so it can
be compared with the UNITREE_G1_SONIC modality config.

    .venv_inference/bin/python mock_policy_server.py --dataset outputs/g1_press_sonic_clean --episode 0
"""
import argparse
import glob
import time

import numpy as np
import pandas as pd
import zmq

from gear_sonic.utils.inference.policy_client import MsgSerializer


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="outputs/g1_press_sonic_clean")
    p.add_argument("--episode", type=int, default=0)
    p.add_argument("--port", type=int, default=5550)
    p.add_argument("--horizon", type=int, default=40)
    p.add_argument("--step", type=int, default=20, help="frames to advance per request (2.5 Hz at 50 Hz = 20)")
    p.add_argument("--loop", action="store_true", help="wrap around at the episode end instead of holding the last chunk")
    a = p.parse_args()

    files = sorted(glob.glob(f"{a.dataset}/data/**/*.parquet", recursive=True))
    df = pd.concat(pd.read_parquet(f) for f in files)
    ep = df[df["episode_index"] == a.episode].sort_values("frame_index")
    tok = np.stack(ep["action.motion_token"].to_numpy()).astype(np.float32)
    lh = np.stack(ep["teleop.left_hand_joints"].to_numpy()).astype(np.float32)
    rh = np.stack(ep["teleop.right_hand_joints"].to_numpy()).astype(np.float32)
    n = len(tok)
    print(f"[mock] episode {a.episode}: {n} frames, token {tok.shape[1]}-dim, hands {lh.shape[1]}+{rh.shape[1]}", flush=True)

    ctx = zmq.Context()
    sock = ctx.socket(zmq.REP)
    sock.bind(f"tcp://*:{a.port}")
    print(f"[mock] PolicyServer protocol on :{a.port}", flush=True)
    cursor, calls, first = 0, 0, True
    while True:
        req = MsgSerializer.from_bytes(sock.recv())
        ep_name = req.get("endpoint", "get_action")
        if ep_name == "ping":
            sock.send(MsgSerializer.to_bytes({"status": "ok", "message": "mock replay server"}))
        elif ep_name == "kill":
            sock.send(MsgSerializer.to_bytes({"status": "ok"}))
            return 0
        elif ep_name == "reset":
            cursor = 0
            sock.send(MsgSerializer.to_bytes({}))
        elif ep_name == "get_modality_config":
            sock.send(MsgSerializer.to_bytes({}))
        elif ep_name == "get_action":
            obs = req["data"]["observation"]
            if first:
                first = False
                print("[mock] first observation:", flush=True)
                for group, val in obs.items():
                    if isinstance(val, dict):
                        for k, v in val.items():
                            shape = getattr(v, "shape", None) or (type(v).__name__ if not isinstance(v, list) else f"list[{len(v)}]")
                            print(f"    {group}.{k}: {shape} {getattr(v, 'dtype', '')}", flush=True)
                    else:
                        print(f"    {group}: {getattr(val, 'shape', val)}", flush=True)
            idx = np.clip(np.arange(cursor, cursor + a.horizon), 0, n - 1)
            action = {
                "action.motion_token": tok[idx][None],
                "action.left_hand_joints": lh[idx][None],
                "action.right_hand_joints": rh[idx][None],
            }
            sock.send(MsgSerializer.to_bytes([action, {"cursor": cursor, "t": time.time()}]))
            calls += 1
            cursor = cursor + a.step
            if cursor >= n:
                cursor = 0 if a.loop else n - 1
            if calls % 10 == 0:
                print(f"[mock] {calls} chunks served, cursor {cursor}/{n}", flush=True)
        else:
            sock.send(MsgSerializer.to_bytes({"error": f"unknown endpoint {ep_name}"}))


if __name__ == "__main__":
    raise SystemExit(main())
