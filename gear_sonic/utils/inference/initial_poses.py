"""Default initial poses for VLA inference.

These arrays are sent to the C++ control loop when the user presses 'i'
to move the robot to a known starting configuration before inference begins.

WARNING: The initial motion token below is specific to the SONIC checkpoint used
during training. Different SONIC checkpoints encode different latent spaces, so
this token will produce a different (and likely incorrect) pose if you switch to
a different SONIC checkpoint. When changing the SONIC checkpoint, you MUST update
LATENT_INITIAL_MOTION_TOKEN to a value that corresponds to a known safe standing
pose in the new checkpoint's latent space.
"""

import numpy as np

# 64-dim motion token for the starting pose of the g1_press_light_switch_sonic demos:
# mean first-frame action.motion_token over the 66 episodes (recorded with the
# policy/low_latency SONIC checkpoint; per-dim std across episodes <= 0.08).
# CHECKPOINT-SPECIFIC: run the C++ deploy with the same low_latency checkpoint.
# The upstream default (sonic v1.x release checkpoint standing pose) is kept below.
LATENT_INITIAL_MOTION_TOKEN = np.array(
    [
        -0.0294, -0.0634, -0.1051,  0.0862,  0.3835,  0.1136, -0.1108,
        -0.0814,  0.0767,  0.1316,  0.0777,  0.0483, -0.4337,  0.1174,
         0.0597,  0.0843, -0.0767,  0.3684,  0.2102, -0.0388,  0.0672,
        -0.1326, -0.2841,  0.1809, -0.1922,  0.0028, -0.0511,  0.2557,
        -0.0767, -0.0417,  0.2263,  0.0199,  0.2860, -0.3191,  0.0966,
         0.0473, -0.0833, -0.0445,  0.1345, -0.0587, -0.1591,  0.1591,
        -0.1449,  0.1458, -0.1619,  0.0180, -0.1231, -0.0095,  0.0057,
        -0.1032, -0.1875, -0.0417,  0.0966, -0.1723, -0.1610, -0.1837,
        -0.2121, -0.0729,  0.0720, -0.1837, -0.1771,  0.0000, -0.1657,
        -0.2339,
    ],
    dtype=np.float32,
)

# Upstream default for the release SONIC checkpoint (not the low-latency one).
LATENT_INITIAL_MOTION_TOKEN_SONIC_RELEASE = np.array(
    [
        -0.0625,  0.0000, -0.0625, -0.1250, -0.1875, -0.0625,  0.1875,
         0.2500,  0.1875, -0.1250,  0.0625, -0.0625, -0.2500, -0.2500,
        -0.3125, -0.0625,  0.0000, -0.0625, -0.1250, -0.1875,  0.0000,
        -0.2500,  0.0000, -0.2500, -0.0625,  0.0625,  0.1250, -0.1250,
         0.2500,  0.1875,  0.2500, -0.1250,  0.1250,  0.1875, -0.0625,
         0.0000, -0.1875, -0.1875,  0.2500,  0.0000,  0.0000, -0.1250,
         0.0625,  0.0000, -0.0625, -0.0625,  0.1875, -0.0625,  0.0000,
         0.0625,  0.1250,  0.0625,  0.1250,  0.0625,  0.1250,  0.0000,
         0.1250,  0.1875,  0.0000,  0.0000,  0.0625,  0.0625,  0.1875,
         0.0625,
    ],
    dtype=np.float32,
)
