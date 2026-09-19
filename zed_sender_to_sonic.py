#!/usr/bin/env python3
"""Feed SONIC's ego_view from the XRoboToolkit video sender instead of opening the ZED twice.

The ZED SDK lets ONE process own the camera. For VR teleop with pass-through, that process
has to be XRoboToolkit's OrinVideoSender (it answers the headset's open-camera command on
13579 and streams stereo H.264 to the headset on 12345). Started with ``--zmq-raw``, the
sender also publishes every captured frame as raw BGRA (12-byte header: width, height,
channels as int32) on a ZMQ PUB socket. This script subscribes to that, keeps the LEFT
eye of the side-by-side image, JPEG-encodes it and republishes it in the exact msgpack
layout ``run-zed-camera.sh`` produced (``{"timestamps": {...}, "images": {"ego_view":
<jpeg bytes>}}``) on port 5555, so the SONIC data exporter, camera viewer and VLA client
work unchanged.

    ./OrinVideoSender --listen 0.0.0.0:13579 --zmq-raw tcp://*:5601      (sender)
    .venv_camera/bin/python zed_sender_to_sonic.py                        (this)
"""
from __future__ import annotations

import argparse
import struct
import time

import cv2
import msgpack
import numpy as np
import zmq


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-endpoint", default="tcp://127.0.0.1:5601", help="OrinVideoSender --zmq-raw endpoint")
    p.add_argument("--port", type=int, default=5555, help="SONIC camera port to publish on")
    p.add_argument("--fps", type=float, default=30.0, help="Publish rate cap (the sender may run at 60)")
    p.add_argument("--eye", choices=["left", "right", "both"], default="left")
    p.add_argument("--out", default="640x480",
                   help="Output size WxH. The SONIC dataset features expect ego_view 640x480 (the exporter refuses "
                        "anything else); 0 keeps the eye's native size.")
    p.add_argument("--fit", choices=["crop", "squash"], default="crop",
                   help="crop = centre-crop to the output aspect then resize (keeps proportions); squash = plain resize")
    p.add_argument("--quality", type=int, default=80)
    p.add_argument("--view", default="ego_view")
    args = p.parse_args()

    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    sub.setsockopt(zmq.CONFLATE, True)
    sub.setsockopt(zmq.RCVHWM, 2)
    sub.connect(args.raw_endpoint)
    pub = ctx.socket(zmq.PUB)
    pub.setsockopt(zmq.SNDHWM, 3)
    pub.bind(f"tcp://*:{args.port}")
    print(f"[zed->sonic] raw frames from {args.raw_endpoint} -> ego_view msgpack on tcp://*:{args.port} ({args.eye} eye, {args.out} {args.fit}, <= {args.fps:g} fps)", flush=True)

    out_w, out_h = (0, 0) if args.out in ("0", "") else tuple(int(v) for v in args.out.lower().split("x"))
    min_dt = 1.0 / args.fps if args.fps > 0 else 0.0
    last = 0.0
    n = 0
    t0 = time.monotonic()
    while True:
        msg = sub.recv()
        now = time.monotonic()
        if now - last < min_dt:
            continue
        if len(msg) < 12:
            continue
        w, h, c = struct.unpack("iii", msg[:12])
        if len(msg) - 12 != w * h * c or c not in (3, 4):
            continue
        img = np.frombuffer(msg, dtype=np.uint8, offset=12).reshape(h, w, c)
        if args.eye != "both" and w >= 2 * h * 0.9:      # side-by-side stereo frame
            half = w // 2
            img = img[:, :half] if args.eye == "left" else img[:, half:]
        if c == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        if out_w and (img.shape[1], img.shape[0]) != (out_w, out_h):
            if args.fit == "crop":
                h0, w0 = img.shape[:2]
                if w0 * out_h > h0 * out_w:        # too wide: trim the sides
                    cw = int(round(h0 * out_w / out_h)); x0 = (w0 - cw) // 2; img = img[:, x0:x0 + cw]
                else:                              # too tall: trim top/bottom
                    ch = int(round(w0 * out_h / out_w)); y0 = (h0 - ch) // 2; img = img[y0:y0 + ch]
            img = cv2.resize(img, (out_w, out_h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", np.ascontiguousarray(img), [int(cv2.IMWRITE_JPEG_QUALITY), int(args.quality)])
        if not ok:
            continue
        stamp = time.time()
        packed = msgpack.packb({"timestamps": {args.view: stamp}, "images": {args.view: buf.tobytes()}}, use_bin_type=True)
        try:
            pub.send(packed, flags=zmq.NOBLOCK)
        except zmq.Again:
            pass
        last = now
        n += 1
        if n % 300 == 0:
            print(f"[zed->sonic] {n / (now - t0):.1f} fps, frame {img.shape[1]}x{img.shape[0]}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
