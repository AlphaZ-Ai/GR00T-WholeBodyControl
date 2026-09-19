# Running a fine-tuned GR00T N1.7 (UNITREE_G1_SONIC) on the G1 from the Thor

Everything runs on the Thor: the Isaac-GR00T **PolicyServer** (`run-gr00t-server.sh`), the
client (`run-vla-inference.sh` -> `gear_sonic/scripts/run_vla_inference.py`), the SONIC C++
controller and the camera. The server can also run on any x86 GPU box instead; then pass its
address to `run-vla-inference.sh`.

## PolicyServer on the Thor (done)

Isaac-GR00T main's Jetson installer refuses this Thor (it checks for Jetson Linux R39 / JetPack
7.2; this board is R38.4 / CUDA 13.0). The Jetson AI Lab tutorial
(https://www.jetson-ai-lab.com/tutorials/groot_n17_on_thor/) pins commit `9c7e746` whose Thor
dependency set is built for CUDA 13.0 from `pypi.jetson-ai-lab.io/sbsa/cu130`; that is what is
installed bare-metal (no Docker, no sudo) in `~/alphaz_ws/Isaac-GR00T`:

- checkout `9c7e746` + the tutorial's TensorRT optimisation patch applied (`git status` shows the
  patched `scripts/deployment/*` files); `code-samples/Dockerfile.libero` is unused.
- `.venv`: `uv sync --project scripts/deployment/thor --no-install-project --extra dev` with
  `/usr/bin/python3.12`, then `uv pip install --no-deps -e .` and the LFS torchcodec wheel.
  torch 2.10.0+cu130, flash-attn 2.8.4, transformers 4.57.6, TensorRT 10.15 (pip).
- NVPL BLAS/LAPACK (needed by the aarch64 torch wheel) extracted from NVIDIA's .deb files into
  `~/opt/nvpl`; `run-gr00t-server.sh` puts it on `LD_LIBRARY_PATH`. FFmpeg is NOT installed
  (needs sudo); it is only needed by torchcodec for dataset video decoding, not for serving.
- `checkpoints/GR00T-N1.7-3B` (6.5 GB base model) downloaded for smoke tests.

Verified: server with the base model + `REAL_G1` tag loads in ~1 min, 6.2 GB GPU, and answers
`get_action` (one 480x640 view, 40-step chunk) in ~175 ms after warm-up in plain PyTorch. The
TensorRT path from the tutorial (~40 ms with NVFP4) is available via
`scripts/deployment/build_trt_pipeline.py` but `run_gr00t_server.py` serves PyTorch only.

## Thor side (done)

- `.venv_inference`: Python 3.12 venv with `gear_sonic` (no deps) + pyzmq, msgpack-numpy,
  numpy 1.26, pin, tyro, opencv, scipy, pandas. `install_scripts/install_inference.sh` cannot be
  used as-is (it builds a Python 3.10 venv and pulls Isaac-GR00T, which needs 3.12 and torch).
- `gear_sonic/utils/inference/policy_client.py`: torch-free copy of Isaac-GR00T's
  `PolicyClient` + `MsgSerializer` (same wire format). `run_vla_inference.py` falls back to it
  when `gr00t` is not importable.
- `gear_sonic/utils/inference/initial_poses.py`: `LATENT_INITIAL_MOTION_TOKEN` is now the mean
  first-frame token of the `g1_press_sonic_clean` demos (low_latency checkpoint). The `i` key
  blends to this pose. The upstream value is kept as `LATENT_INITIAL_MOTION_TOKEN_SONIC_RELEASE`.
- `run-vla-inference.sh <policy-host> ["prompt"]` and `keyboard_publisher.py` (keys on :5580).
- `mock_policy_server.py`: replays a recorded episode's action chunks with the PolicyServer
  protocol; used to verify the chain without a GPU (see below).

Verified in the MuJoCo sim (headless, `--enable-image-publish`) with the low-latency C++
controller on `lo` (`--disable-crc-check`) and the mock server: the client built the observation
with exactly the UNITREE_G1_SONIC modality keys (video.ego_view 480x640, state left_leg/right_leg/
waist/left_arm/right_arm/left_hand/right_hand/projected_gravity, language), received chunks at
2.5 Hz, and the controller consumed protocol-v4 tokens plus the 7-value hand vectors while the sim
robot tracked them.

## Checking a checkpoint before a robot run

`check_policy_on_demo.py` feeds recorded demo frames + states to the running server and compares
the returned 40-step token chunk with the demo's own next tokens (plus the hand command):
```bash
./.venv_inference/bin/python check_policy_on_demo.py --episode 0 --frames 0,100,200,300,400,500
```
Result for `~/alphaz_ws/checkpoints/checkpoint-5000` (2026-09-18): loads in ~30 s, 6.4 GB GPU,
~155 ms per chunk; tokens within the 1.25 bound (max 0.5); token MAE vs demo 0.011-0.043, better
than a hold-last-token baseline on moving segments (frames 100/500) and about equal on static
ones; right-hand slot 4 predicted 1.5 (closed) wherever the demo was closed.

## Starting the server

On the Thor:
```bash
./run-gr00t-server.sh <checkpoint dir or HF model id>      # UNITREE_G1_SONIC, port 5550
```
Or on an x86 GPU box (then use its address as `<policy-host>` below)

```bash
git clone https://github.com/NVIDIA/Isaac-GR00T.git && cd Isaac-GR00T && uv sync   # x86_64, CUDA 12.8
uv run python gr00t/eval/run_gr00t_server.py \
    --model-path /path/to/checkpoint-XXXX      # or a Hugging Face model id \
    --embodiment-tag UNITREE_G1_SONIC --device cuda:0 --port 5550
```
Open port 5550 to the Thor (Tailscale: use the machine's 100.x address as `<policy-host>`).

## Run on the robot

Terminals on the Thor, in order (robot supported, e-stop in reach):
```bash
./run-sonic-hardware-lowlatency.sh enP2p1s0 dex1 --dex1-swap-sides   # SAME checkpoint as the demos
./run-zed-camera.sh                                                  # ego_view on :5555 (or run-zed-headset.sh)
./run-vla-inference.sh localhost "press the light switch"      # or the GPU box's address
.venv_inference/bin/python keyboard_publisher.py
```
In the keyboard terminal: `k` (start controller, PLANNER mode), `]` then `i` (right gripper closed,
blend to the demo start pose, POSE mode), `p` (run the policy). `p` pauses, `k` stops. The prompt
must be the dataset's task string ("press the light switch"). Optional recording of the run:
`.venv_data_collection/bin/python gear_sonic/scripts/run_data_exporter.py --task-prompt "press the light switch"`
and `c` in the keyboard terminal to start and again to stop+save (`x` discards).

Notes
- The 7+7 hand vectors are SONIC's fixed format; the Dex1 adapter reads closure from slot 4. The
  demos' right-hand state carries the measured Dex1 angle in slot 4 (open about 5.0 rad, closed
  about 0.1), so the Dex1 service must be up before the controller so the state matches training.
- The token latent space is checkpoint-specific: deploy with `policy/low_latency`, not v1.1.
- Action bound: the client drops a chunk whose |token| exceeds 1.25 (prints a warning).
