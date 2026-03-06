"""
Inspire FTP dexterous hand controller for GR00T whole-body teleoperation.

Trigger-based open/close mode: VR controller trigger maps directly to hand
closure, no full finger-tracking retargeting required.

DDS topics (Inspire FTP firmware):
  rt/inspire_hand/ctrl/l  — left hand command
  rt/inspire_hand/ctrl/r  — right hand command
  rt/inspire_hand/state/l — left hand state
  rt/inspire_hand/state/r — right hand state

Usage:
    from multiprocessing import Value
    from gear_sonic.utils.teleop.inspire_hand_controller import InspireFTPController

    left_trigger  = Value('d', 0.0)   # 0.0=fully open, 1.0=fully closed
    right_trigger = Value('d', 0.0)
    pause_flag    = Value('b', False)  # True forces both hands open

    ctrl = InspireFTPController(
        left_gripper_value=left_trigger,
        right_gripper_value=right_trigger,
        hand_pause_flag=pause_flag,
    )
"""

import threading
import time
from enum import IntEnum
from multiprocessing import Array, Process, Value

import numpy as np

# ---------------------------------------------------------------------------
# DDS topic names
# ---------------------------------------------------------------------------
_TOPIC_LEFT_CMD   = "rt/inspire_hand/ctrl/l"
_TOPIC_RIGHT_CMD  = "rt/inspire_hand/ctrl/r"
_TOPIC_LEFT_STATE = "rt/inspire_hand/state/l"
_TOPIC_RIGHT_STATE = "rt/inspire_hand/state/r"

NUM_MOTORS = 6


class InspireRightHandJointIndex(IntEnum):
    kRightHandPinky         = 0
    kRightHandRing          = 1
    kRightHandMiddle        = 2
    kRightHandIndex         = 3
    kRightHandThumbBend     = 4
    kRightHandThumbRotation = 5


class InspireLeftHandJointIndex(IntEnum):
    kLeftHandPinky         = 0
    kLeftHandRing          = 1
    kLeftHandMiddle        = 2
    kLeftHandIndex         = 3
    kLeftHandThumbBend     = 4
    kLeftHandThumbRotation = 5


class InspireFTPController:
    """Controls Inspire FTP dexterous hands via DDS using VR trigger input.

    All DDS initialisation happens inside a daemon subprocess so this class
    is safe to instantiate from the main teleop process.

    Shared-memory convention for gripper values:
        0.0  = fully open
        1.0  = fully closed

    Args:
        left_gripper_value:  multiprocessing.Value('d', 0.0)
        right_gripper_value: multiprocessing.Value('d', 0.0)
        hand_pause_flag:     multiprocessing.Value('b', False)
            When True both hands are forced to their open pose regardless of
            trigger inputs.  Set to True whenever the policy is not running.
        fps:               Control loop frequency in Hz (default 100).
        network_interface: DDS network interface (default 'enP8p1s0').
        domain_id:         DDS domain id (default 0).
    """

    LEFT_OPEN_POSE   = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float64)
    LEFT_CLOSED_POSE = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float64)

    RIGHT_OPEN_POSE = np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float64)
    # RIGHT_OPEN_POSE   = np.array([0.0, 0.0, 0.0, 0.0, 0.7, 0.0], dtype=np.float64)
    RIGHT_CLOSED_POSE = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 1.0], dtype=np.float64)

    def __init__(
        self,
        left_gripper_value,
        right_gripper_value,
        hand_pause_flag=None,
        fps: float = 100.0,
        network_interface: str = "enP8p1s0",
        domain_id: int = 0,
    ):
        self.fps = fps
        self.network_interface = network_interface
        self.domain_id = domain_id

        # Shared arrays for hand state readback (normalised [0,1])
        self.left_hand_state_array  = Array('d', NUM_MOTORS, lock=True)
        self.right_hand_state_array = Array('d', NUM_MOTORS, lock=True)

        proc = Process(
            target=self._run,
            args=(
                left_gripper_value,
                right_gripper_value,
                self.left_hand_state_array,
                self.right_hand_state_array,
                hand_pause_flag,
            ),
            daemon=True,
        )
        proc.start()
        print("[InspireFTPController] Controller process started.")

    # ------------------------------------------------------------------
    # Subprocess entry point — all DDS work happens here
    # ------------------------------------------------------------------

    def _run(
        self,
        left_gripper_value,
        right_gripper_value,
        left_hand_state_array,
        right_hand_state_array,
        hand_pause_flag,
    ):
        from unitree_sdk2py.core.channel import (
            ChannelFactoryInitialize,
            ChannelPublisher,
            ChannelSubscriber,
        )
        from inspire_sdkpy import inspire_dds
        import inspire_sdkpy.inspire_hand_defaut as inspire_hand_default

        ChannelFactoryInitialize(self.domain_id, self.network_interface)

        left_pub  = ChannelPublisher(_TOPIC_LEFT_CMD,  inspire_dds.inspire_hand_ctrl)
        left_pub.Init()
        right_pub = ChannelPublisher(_TOPIC_RIGHT_CMD, inspire_dds.inspire_hand_ctrl)
        right_pub.Init()

        left_sub  = ChannelSubscriber(_TOPIC_LEFT_STATE,  inspire_dds.inspire_hand_state)
        left_sub.Init()
        right_sub = ChannelSubscriber(_TOPIC_RIGHT_STATE, inspire_dds.inspire_hand_state)
        right_sub.Init()

        # Flags used inside the subscribe thread (list so closure can mutate them)
        left_received  = [False]
        right_received = [False]

        def _subscribe():
            while True:
                lmsg = left_sub.Read()
                if (
                    lmsg is not None
                    and hasattr(lmsg, "angle_act")
                    and len(lmsg.angle_act) == NUM_MOTORS
                ):
                    with left_hand_state_array.get_lock():
                        for i in range(NUM_MOTORS):
                            left_hand_state_array[i] = lmsg.angle_act[i] / 1000.0
                    left_received[0] = True

                rmsg = right_sub.Read()
                if (
                    rmsg is not None
                    and hasattr(rmsg, "angle_act")
                    and len(rmsg.angle_act) == NUM_MOTORS
                ):
                    with right_hand_state_array.get_lock():
                        for i in range(NUM_MOTORS):
                            right_hand_state_array[i] = rmsg.angle_act[i] / 1000.0
                    right_received[0] = True

                time.sleep(0.002)

        sub_thread = threading.Thread(target=_subscribe, daemon=True)
        sub_thread.start()

        # Wait for initial state messages (5 s timeout)
        wait = 0
        while not (left_received[0] and right_received[0]):
            if wait % 100 == 0:
                print(
                    f"[InspireFTPController] Waiting for hand states "
                    f"(L:{left_received[0]} R:{right_received[0]})..."
                )
            time.sleep(0.01)
            wait += 1
            if wait > 500:
                print("[InspireFTPController] Timeout waiting for initial state, proceeding.")
                break
        print("[InspireFTPController] DDS state subscription ready.")

        left_open   = self.LEFT_OPEN_POSE.copy()
        left_closed = self.LEFT_CLOSED_POSE.copy()
        right_open   = self.RIGHT_OPEN_POSE.copy()
        right_closed = self.RIGHT_CLOSED_POSE.copy()

        dds_ok_logged    = False
        dds_last_warn_t  = 0.0
        debug_count      = 0

        def _send(left_q: np.ndarray, right_q: np.ndarray):
            nonlocal dds_ok_logged, dds_last_warn_t, debug_count

            left_cmd  = inspire_hand_default.get_inspire_hand_ctrl()
            right_cmd = inspire_hand_default.get_inspire_hand_ctrl()

            left_cmd.angle_set  = [int(np.clip(v * 1000, 0, 1000)) for v in left_q]
            right_cmd.angle_set = [int(np.clip(v * 1000, 0, 1000)) for v in right_q]
            left_cmd.mode  = 0b0001
            right_cmd.mode = 0b0001

            lok = left_pub.Write(left_cmd)
            rok = right_pub.Write(right_cmd)

            now = time.time()
            if lok and rok:
                if not dds_ok_logged:
                    print("[InspireFTPController] DDS publishers connected.")
                    dds_ok_logged = True
            else:
                if now - dds_last_warn_t >= 1.0:
                    print(
                        f"[InspireFTPController] No DDS subscriber "
                        f"(L={lok} R={rok}). Is the inspire hand driver running?"
                    )
                    dds_last_warn_t = now
                    dds_ok_logged = False

            if debug_count < 20:
                print(
                    f"[InspireFTPController] cmd "
                    f"L={left_cmd.angle_set} R={right_cmd.angle_set}"
                )
                debug_count += 1

        while True:
            t0 = time.time()

            is_paused = False
            if hand_pause_flag is not None:
                with hand_pause_flag.get_lock():
                    is_paused = bool(hand_pause_flag.value)

            if is_paused:
                left_q  = left_open.copy()
                right_q = right_open.copy()
            else:
                with left_gripper_value.get_lock():
                    lt = float(np.clip(left_gripper_value.value,  0.0, 1.0))
                with right_gripper_value.get_lock():
                    rt = float(np.clip(right_gripper_value.value, 0.0, 1.0))

                left_q  = left_open  * (1.0 - lt) + left_closed  * lt
                right_q = right_open * (1.0 - rt) + right_closed * rt

            _send(left_q, right_q)

            elapsed = time.time() - t0
            time.sleep(max(0.0, 1.0 / self.fps - elapsed))
