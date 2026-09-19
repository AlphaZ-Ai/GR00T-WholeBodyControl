"""ZED Mini/USB ZED RGB driver using the separately installed ZED SDK.

Publishes one rectified eye as RGB under the standard SONIC camera mount key.
Depth is disabled: SONIC's ImageMessageSchema carries RGB images, not depth.
"""

from dataclasses import dataclass
import time

import cv2

from gear_sonic.camera.sensor import Sensor
from gear_sonic.camera.sensor_server import CameraMountPosition, ImageMessageSchema


@dataclass
class ZEDConfig:
    resolution: str = "HD720"
    fps: int = 30
    view: str = "left"
    flip: bool = False
    output: str = "640x480"
    """Output size WxH. The SONIC datasets/VLA expect ego_view 640x480: the eye image is centre-cropped
    to the output aspect (16:9 -> 4:3 keeps the middle 960x720 of HD720) and resized. "0" = native."""


class ZEDSensor(Sensor):
    def __init__(self, config=None, mount_position=CameraMountPosition.EGO_VIEW.value,
                 device_id=None):
        try:
            import pyzed.sl as sl
        except ImportError as exc:
            raise ImportError("ZED requires the ZED SDK and its matching pyzed wheel. "
                              "Use this checkout's .venv_camera environment.") from exc

        self.config = config or ZEDConfig()
        self.mount_position = mount_position
        if self.config.view not in ("left", "right"):
            raise ValueError("ZED view must be left or right")
        if self.config.resolution not in ("HD720", "HD1080", "HD2K", "VGA"):
            raise ValueError("ZED resolution must be HD720, HD1080, HD2K or VGA")
        self.sl = sl
        out = (self.config.output or "0").lower()
        self.out_size = None if out in ("0", "native", "") else tuple(int(v) for v in out.split("x"))
        self.camera = sl.Camera()
        self.image = sl.Mat()
        self.runtime = sl.RuntimeParameters()
        self.view = sl.VIEW.LEFT if self.config.view == "left" else sl.VIEW.RIGHT
        params = sl.InitParameters()
        params.camera_resolution = getattr(sl.RESOLUTION, self.config.resolution)
        params.camera_fps = self.config.fps
        params.depth_mode = sl.DEPTH_MODE.NONE
        params.camera_image_flip = sl.FLIP_MODE.ON if self.config.flip else sl.FLIP_MODE.OFF
        params.open_timeout_sec = 5.0
        if device_id is not None:
            params.set_from_serial_number(int(device_id))
        try:
            status = self.camera.open(params)
            if status != sl.ERROR_CODE.SUCCESS:
                raise RuntimeError(f"ZED camera {device_id or '(auto)'} open failed: {status}")
        except Exception:
            self.close()
            raise

    def read(self):
        if self.camera.grab(self.runtime) != self.sl.ERROR_CODE.SUCCESS:
            return None
        if self.camera.retrieve_image(self.image, self.view) != self.sl.ERROR_CODE.SUCCESS:
            return None
        # cvtColor owns the output: the SDK reuses its Mat on the next grab.
        rgb = cv2.cvtColor(self.image.get_data(), cv2.COLOR_BGRA2RGB)
        if self.out_size and (rgb.shape[1], rgb.shape[0]) != self.out_size:
            ow, oh = self.out_size
            h0, w0 = rgb.shape[:2]
            if w0 * oh > h0 * ow:      # too wide: trim the sides (same crop as zed_sender_to_sonic.py)
                cw = int(round(h0 * ow / oh)); x0 = (w0 - cw) // 2; rgb = rgb[:, x0:x0 + cw]
            else:                      # too tall: trim top/bottom
                ch = int(round(w0 * oh / ow)); y0 = (h0 - ch) // 2; rgb = rgb[y0:y0 + ch]
            rgb = cv2.resize(rgb, (ow, oh), interpolation=cv2.INTER_AREA)
        return {"timestamps": {self.mount_position: time.time()},
                "images": {self.mount_position: rgb}}

    def serialize(self, data):
        return ImageMessageSchema(**data).serialize()

    def observation_space(self):
        return None

    def close(self):
        self.camera.close()
