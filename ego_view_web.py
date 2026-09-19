#!/usr/bin/env python3
"""Show the robot's ego view (the ZED Mini) in the PICO headset's browser.

Neither SONIC nor the XRoboToolkit SDK pushes robot video to the headset (the SDK only
receives the headset's own cameras), so this republishes the camera server's ZMQ stream
(``run-zed-camera.sh``, port 5555, msgpack + JPEG) as a plain web page with an MJPEG
stream. Open it in the PICO's browser and pin the window in front of you:

    http://10.0.2.87:8090/          (the Thor's LAN address)

Run on the Thor next to the camera server:

    .venv_camera/bin/python ego_view_web.py               # ZMQ localhost:5555 -> http://0.0.0.0:8090
    .venv_camera/bin/python ego_view_web.py --port 8090 --camera-port 5555 --view ego_view

The JPEG bytes are forwarded as-is (no re-encode) when the server sends raw JPEG, so
the added latency is the Wi-Fi link plus browser decode. 2D only: the camera server
publishes one rectified eye.
"""
from __future__ import annotations

import argparse
import base64
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import msgpack
import msgpack_numpy as m
import zmq

PAGE = """<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>G1 ego view</title><style>
html,body{margin:0;height:100%;background:#000;overflow:hidden}
img{width:100vw;height:100vh;object-fit:contain;display:block}
#hud{position:fixed;left:8px;top:8px;color:#8f8;font:14px monospace;background:rgba(0,0,0,.4);padding:2px 6px}
</style></head><body><img id="v" src="/stream"><div id="hud">G1 ego view</div>
<script>
const img=document.getElementById('v'),hud=document.getElementById('hud');let n=0,t=Date.now();
img.addEventListener('load',()=>{n++;const d=Date.now()-t;if(d>2000){hud.textContent='G1 ego view  '+(1000*n/d).toFixed(1)+' fps';n=0;t=Date.now();}});
img.addEventListener('error',()=>{hud.textContent='stream lost, reconnecting';setTimeout(()=>{img.src='/stream?'+Date.now()},1000)});
</script></body></html>"""


class Latest:
    def __init__(self) -> None:
        self.jpeg: bytes | None = None
        self.seq = 0
        self.stamp = 0.0
        self.cond = threading.Condition()

    def set(self, jpeg: bytes) -> None:
        with self.cond:
            self.jpeg = jpeg
            self.seq += 1
            self.stamp = time.monotonic()
            self.cond.notify_all()

    def wait_next(self, seq: int, timeout: float = 2.0) -> tuple[int, bytes | None]:
        with self.cond:
            if self.seq == seq:
                self.cond.wait(timeout)
            return self.seq, self.jpeg


def subscriber(latest: Latest, host: str, port: int, view: str) -> None:
    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt_string(zmq.SUBSCRIBE, "")
    sock.setsockopt(zmq.CONFLATE, True)
    sock.setsockopt(zmq.RCVHWM, 3)
    sock.connect(f"tcp://{host}:{port}")
    print(f"[ego-view-web] subscribed to tcp://{host}:{port}, view '{view}'", flush=True)
    frames = 0
    t0 = time.monotonic()
    while True:
        packed = sock.recv()
        data = msgpack.unpackb(packed, object_hook=m.decode)
        images = data.get("images", {}) if isinstance(data, dict) else {}
        value = images.get(view)
        if value is None and images:
            value = next(iter(images.values()))
        if value is None:
            continue
        if isinstance(value, str):
            jpeg = base64.b64decode(value)
        elif isinstance(value, (bytes, bytearray)):
            jpeg = bytes(value)
        else:
            import cv2  # ndarray fallback (RGB)

            ok, buf = cv2.imencode(".jpg", value[..., ::-1], [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if not ok:
                continue
            jpeg = buf.tobytes()
        latest.set(jpeg)
        frames += 1
        if frames % 300 == 0:
            print(f"[ego-view-web] {frames / (time.monotonic() - t0):.1f} fps from the camera server", flush=True)


def make_handler(latest: Latest):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/snapshot.jpg":
                _, jpeg = latest.wait_next(-1, timeout=2.0)
                if jpeg is None:
                    self.send_error(503, "no frame yet")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpeg)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(jpeg)
            elif path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seq = -1
                try:
                    while True:
                        seq, jpeg = latest.wait_next(seq, timeout=2.0)
                        if jpeg is None:
                            continue
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            else:
                self.send_error(404)

    return Handler


def main() -> int:
    p = argparse.ArgumentParser(description="Ego view (ZED) -> MJPEG web page for the headset browser")
    p.add_argument("--camera-host", default="localhost")
    p.add_argument("--camera-port", type=int, default=5555)
    p.add_argument("--view", default="ego_view", help="image key in the camera server message")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8090)
    args = p.parse_args()
    latest = Latest()
    threading.Thread(target=subscriber, args=(latest, args.camera_host, args.camera_port, args.view), daemon=True).start()
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(latest))
    print(f"[ego-view-web] open http://<thor-ip>:{args.port}/ in the headset browser (Ctrl-C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
