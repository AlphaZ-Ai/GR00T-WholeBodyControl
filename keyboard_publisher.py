#!/usr/bin/env python3
"""Keyboard publisher for run_vla_inference.py (ZMQ PUB on 5580), standalone.

Same protocol launch_inference.py's tmux pane uses. Type a key + Enter:
  k  start/stop the C++ control loop      i  blend to the initial pose (POSE mode)
  p  pause/resume the policy loop         [ / ]  toggle left/right hand closed for the initial pose
  t <text>  change the prompt             c  data exporter start / stop+save (toggle)   x  discard the episode
"""
import sys
import time

import zmq

port = int(sys.argv[1]) if len(sys.argv) > 1 else 5580
ctx = zmq.Context()
pub = ctx.socket(zmq.PUB)
pub.bind(f"tcp://*:{port}")
time.sleep(0.5)
print(f"Keyboard publisher on :{port}. Keys: k=start/stop loop, i=initial pose, p=pause/resume, [ ]=hands, t <prompt>, c=record start/stop, x=discard", flush=True)
while True:
    try:
        key = input()
    except EOFError:
        break
    if key.startswith("t "):
        pub.send_string("prompt:" + key[2:])
        print("Sent prompt:", key[2:], flush=True)
    elif key:
        pub.send_string(key)
        print("Sent:", key, flush=True)
