"""ZED contract tests with a fake SDK camera; no physical device is opened."""
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from gear_sonic.camera.composed_camera import ComposedCameraConfig, ComposedCameraSensor
from gear_sonic.camera.drivers.zed import ZEDConfig, ZEDSensor
from gear_sonic.camera.sensor_server import ImageMessageSchema


@pytest.fixture
def sdk(monkeypatch):
    frame = np.full((8, 8, 4), [10, 30, 220, 255], dtype=np.uint8)

    class Camera:
        def __init__(self):
            self.closed = False
            self.status = 0

        def open(self, params):
            self.params = params
            return fake.open_status

        def close(self):
            self.closed = True

        def grab(self, runtime):
            return self.status

        def retrieve_image(self, image, view):
            self.view = view
            return self.status

    class Params:
        def set_from_serial_number(self, serial):
            self.serial = serial

    fake = SimpleNamespace(
        Camera=Camera, InitParameters=Params, RuntimeParameters=SimpleNamespace,
        Mat=lambda: SimpleNamespace(get_data=lambda: frame),
        VIEW=SimpleNamespace(LEFT=1, RIGHT=2),
        RESOLUTION=SimpleNamespace(HD720=720, HD1080=1080, HD2K=2000, VGA=480),
        DEPTH_MODE=SimpleNamespace(NONE=0), FLIP_MODE=SimpleNamespace(ON=1, OFF=0),
        ERROR_CODE=SimpleNamespace(SUCCESS=0), open_status=0, frame=frame,
    )
    monkeypatch.setitem(sys.modules, "pyzed", SimpleNamespace(sl=fake))
    monkeypatch.setitem(sys.modules, "pyzed.sl", fake)
    return fake


def test_rgb_copy_and_wire_schema(sdk):
    camera = ZEDSensor(device_id="12345")
    assert camera.camera.params.serial == 12345
    assert camera.camera.params.depth_mode == 0
    reading = camera.read()
    key = camera.mount_position
    np.testing.assert_array_equal(reading["images"][key][0, 0], [220, 30, 10])
    sdk.frame[:] = 0
    np.testing.assert_array_equal(reading["images"][key][0, 0], [220, 30, 10])
    decoded = ImageMessageSchema.deserialize(camera.serialize(reading))
    assert decoded.images[key].shape == (8, 8, 3)
    np.testing.assert_allclose(decoded.images[key][0, 0], [220, 30, 10], atol=3)
    camera.close()
    assert camera.camera.closed


def test_factory_passes_zed_configuration(sdk):
    factory = object.__new__(ComposedCameraSensor)
    factory.config = ComposedCameraConfig(zed_view="right", zed_flip=True, fps=60)
    camera = factory._instantiate_camera("ego_view", "zed", "42")
    camera.read()
    assert camera.camera.view == sdk.VIEW.RIGHT
    assert camera.camera.params.camera_fps == 60
    assert camera.camera.params.camera_image_flip == sdk.FLIP_MODE.ON
    assert camera.camera.params.serial == 42


def test_grab_failure_is_not_an_old_frame(sdk):
    camera = ZEDSensor()
    assert camera.read() is not None
    camera.camera.status = 1
    assert camera.read() is None


def test_open_failure_reports_device(sdk):
    sdk.open_status = "CAMERA NOT DETECTED"
    with pytest.raises(RuntimeError, match="123.*CAMERA NOT DETECTED"):
        ZEDSensor(device_id="123")


def test_invalid_view_rejected(sdk):
    with pytest.raises(ValueError, match="view"):
        ZEDSensor(ZEDConfig(view="stereo"))
