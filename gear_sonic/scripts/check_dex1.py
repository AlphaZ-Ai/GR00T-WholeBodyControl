"""Read-only Dex1 state probe. Creates subscribers only; never motor publishers."""
import argparse
import math
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize, ChannelSubscriber
from unitree_sdk2py.idl.unitree_go.msg.dds_ import MotorStates_
from unitree_sdk2py.idl.unitree_hg.msg.dds_ import LowState_


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", required=True)
    parser.add_argument("--hand-type", choices=("dex1", "dex1-internal"), required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    ChannelFactoryInitialize(0, args.interface)
    if args.hand_type == "dex1-internal":
        topics = [("rt/lowstate", LowState_)]
    else:
        topics = [(f"rt/dex1/{side}/state", MotorStates_) for side in ("left", "right")]
    for topic, kind in topics:
        subscriber = ChannelSubscriber(topic, kind)
        subscriber.Init()
        deadline = time.monotonic() + args.timeout
        sample = None
        while sample is None and time.monotonic() < deadline:
            sample = subscriber.Read(0.1)
        if sample is None:
            raise SystemExit(f"No feedback on {topic}; check wiring, interface and robot/service power")
        motors = [sample.motor_state[i] for i in (31, 33)] if args.hand_type == "dex1-internal" else sample.states
        if len(motors) != (2 if args.hand_type == "dex1-internal" else 1):
            raise SystemExit(f"Unexpected motor count on {topic}")
        for i, motor in enumerate(motors):
            if not math.isfinite(motor.q) or not math.isfinite(motor.dq):
                raise SystemExit(f"Invalid feedback on {topic}")
            print(f"{topic} motor {i}: q={motor.q:.4f} rad, dq={motor.dq:.4f} rad/s")
        subscriber.Close()
    print("State received. This does not verify gripper actuation or calibration.")


if __name__ == "__main__":
    main()
