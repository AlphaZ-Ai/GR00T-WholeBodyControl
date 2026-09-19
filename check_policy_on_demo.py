#!/usr/bin/env python3
"""Open-loop check of a served GR00T policy against a recorded SONIC episode.

Feeds real demo frames + states (exactly as run_vla_inference.py builds them) to the
PolicyServer and compares the returned 40-step motion-token chunk with the demo's own next
40 tokens. Prints latency, action bound and per-frame error vs. a "hold last token" baseline.

    .venv_inference/bin/python check_policy_on_demo.py --episode 0 --frames 0,100,200,300,400
"""
import argparse, glob, json, time
import cv2, numpy as np, pandas as pd
from gear_sonic.utils.inference.policy_client import PolicyClient


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="outputs/g1_press_sonic_clean")
    p.add_argument("--episode", type=int, default=0)
    p.add_argument("--frames", default="0,100,200,300,400,500")
    p.add_argument("--host", default="localhost"); p.add_argument("--port", type=int, default=5550)
    p.add_argument("--prompt", default="press the light switch")
    a = p.parse_args()
    mod = json.load(open(f"{a.dataset}/meta/modality.json"))["state"]
    df = pd.concat(pd.read_parquet(f) for f in sorted(glob.glob(f"{a.dataset}/data/**/*.parquet", recursive=True)))
    ep = df[df["episode_index"] == a.episode].sort_values("frame_index").reset_index(drop=True)
    tok = np.stack(ep["action.motion_token"].to_numpy()).astype(np.float32)
    st = np.stack(ep["observation.state"].to_numpy()).astype(np.float32)
    pg = np.stack(ep["observation.projected_gravity"].to_numpy()).astype(np.float32)
    rh = np.stack(ep["teleop.right_hand_joints"].to_numpy()).astype(np.float32)
    vid = glob.glob(f"{a.dataset}/videos/**/observation.images.ego_view/episode_{a.episode:06d}.mp4", recursive=True)[0]
    cap = cv2.VideoCapture(vid)
    c = PolicyClient(host=a.host, port=a.port, timeout_ms=60000)
    print("ping", c.ping())
    keys = ["left_leg", "right_leg", "waist", "left_arm", "right_arm", "left_hand", "right_hand"]
    for f in [int(x) for x in a.frames.split(",")]:
        if f >= len(ep): continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, f); ok, bgr = cap.read()
        if not ok: print("frame", f, "no video frame"); continue
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        obs = {"video": {"ego_view": rgb[None, None]},
               "state": {k: st[f, mod[k]["start"]:mod[k]["end"]][None, None] for k in keys},
               "language": {"annotation.human.task_description": [[a.prompt]]}}
        obs["state"]["projected_gravity"] = pg[f][None, None]
        t = time.time(); action, info = c.get_action(obs); dt = time.time() - t
        pred = np.asarray(action.get("action.motion_token", action.get("motion_token")))[0]
        hand = np.asarray(action.get("action.right_hand_joints", action.get("right_hand_joints")))[0]
        idx = np.clip(np.arange(f, f + len(pred)), 0, len(tok) - 1)
        gt = tok[idx]
        err = np.abs(pred - gt).mean(); hold = np.abs(tok[f][None] - gt).mean()
        print(f"frame {f:4d}: {dt*1000:6.0f} ms | |tok|max {np.abs(pred).max():.3f} | MAE vs demo {err:.4f} (hold-last baseline {hold:.4f}) "
              f"| hand[4] pred {hand[:, 4].mean():.2f} demo {rh[idx, 4].mean():.2f}")


if __name__ == "__main__":
    main()
