# SONIC V1.1 installation on this Thor

Installed on 2026-09-12 in `/home/azthor/alphaz_ws/GR00T-WholeBodyControl`.
Source: `https://github.com/AlphaZ-Ai/GR00T-WholeBodyControl.git`, commit
`087f9ac` (matched `origin/main` at installation). Git LFS assets were fetched.

For the subsequently added Dex1_1 gripper and ZED Mini integration, see
[DEX1_ZED_SETUP.md](DEX1_ZED_SETUP.md). It records the additional installation,
validation and outstanding physical-hardware checks.

## Run in MuJoCo

Open two terminals in this repository.

Terminal 1:

```bash
./run-sonic-sim.sh
```

Terminal 2:

```bash
./run-sonic-v1.1.sh
```

In the controller terminal, press `]` to start control. In the MuJoCo viewer,
press `9` to release the suspension. In the controller terminal, press `T` to
play the reference motion, `N`/`P` to select motions, and `O` to stop.
Enter toggles planner mode. Stop the simulator with Ctrl+C.

For headless simulation, use `./run-sonic-sim.sh --no-enable-onscreen`.
The provided controller launcher uses loopback (`lo`), keyboard input, the
matching V1.1 encoder/decoder/observation config, and ankle-pitch Kp/Kd scales
`4,10=1.5`. Engines are cached, although loading/hashing models still takes time.

## Installed components

- Python 3.10.20 simulation environment: `.venv_sim`.
- `gear_sonic[sim]` and the repository's editable Unitree SDK2 Python package.
- PyTorch 2.14.0+cu130, MuJoCo 3.13.0, Pinocchio 2.7.0,
  NumPy 1.26.4, SciPy 1.15.3 and CycloneDDS Python 0.10.2.
- C++ controller: `gear_sonic_deploy/target/release/g1_deploy_onnx_ref`.
- Existing CUDA 13.0 and system TensorRT 10.13.3.9 development/runtime libraries.
- Existing ONNX Runtime 1.16.3 at `/home/azthor/opt/onnxruntime`.
- Existing CycloneDDS at `/home/azthor/opt/cyclonedds` and supplemental C++
  headers at `/home/azthor/opt/include`.
- Local `just` 1.43.0 in `.local/sonic-v1.1/bin`.
- Model download/validation environment: `.venv_models`, including
  `huggingface_hub`, ONNX, ONNX Runtime and matching TensorRT Python bindings.
- V1.1 ONNX files/config: `gear_sonic_deploy/policy/sonic_v1_1/`.
- Planner: `gear_sonic_deploy/planner/target_vel/V2/planner_sonic.onnx`.
- All three `.trt` engines compiled locally for NVIDIA Thor.

`sonic-env.sh` sets these paths for the current shell. It does not modify your
shell profile. The launchers source it automatically. The installation used
existing system packages and user-owned directories; no sudo was required.

The upstream simulator initialized the same DDS domain in both `SimWrapper`
and `BaseSimulator`. The redundant initialization in
`gear_sonic/scripts/run_sim_loop.py` was removed; `BaseSimulator` owns it.

## Validation

- Full CMake Release build succeeded with GCC 13.3; Thor detection correctly
  disabled Orin-specific DLA linkage. No missing shared libraries.
- Python imports succeeded; an actual PyTorch GPU matrix multiplication
  completed on NVIDIA Thor with finite results.
- All three ONNX models passed `onnx.checker`; encoder and decoder CPU
  inference returned finite outputs of shapes `(1, 64)` and `(1, 29)`.
- All three locally compiled TensorRT engines loaded successfully using
  TensorRT 10.13.3.9.
- Headless MuJoCo published 50 consecutive finite DDS state messages.
- The C++ V1.1 controller entered CONTROL mode and ran against MuJoCo;
  100 state messages and 100 motor-command messages had finite joint
  positions and velocities. Typical logged policy inference was about
  2.1 ms; this is a smoke-test observation, not a real-time guarantee.
- Planner initialization and its first inference succeeded (about 20 ms).
- Controller stopped normally through its keyboard interface; simulator
  stopped with Ctrl+C.

Two validation limitations remain:

1. The repository's FK unit test hardcodes the absent fixture directory
   `reference/bones_072925_test/`. The test attempt failed; it is not counted
   as a pass. Integration checks above use the included `reference/example`.
2. `uv pip check` flags NVIDIA's cuSPARSELt wheel platform metadata
   (`manylinux2014_sbsa`). Its bundled library is ARM64 and loads successfully,
   and PyTorch CUDA computation passed. The vendor metadata was left intact.

This installation covers C++ SONIC V1.1 deployment and MuJoCo simulation.
Physical-robot motion, headset teleoperation, cameras, VLA services and Isaac
Lab training were not tested or installed as part of this setup. The deployment
guide's Jetson version matrix describes Orin; this Thor used its installed
TensorRT 10.13.3.9 and was verified in simulation, not on hardware.

## Rebuild and maintenance

```bash
source sonic-env.sh
cmake -S gear_sonic_deploy -B gear_sonic_deploy/build \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
  -DCMAKE_PREFIX_PATH="$onnxruntime_ROOT" \
  -DCMAKE_CXX_FLAGS=-I/home/azthor/opt/include \
  -DMSGPACK_INCLUDE_DIR=/home/azthor/opt/include \
  -DCUDAToolkit_ROOT="$CUDAToolkit_ROOT"
cmake --build gear_sonic_deploy/build -j 6
```

Refresh the matching models with:

```bash
.venv_models/bin/python download_from_hf.py --sonic-v1-1
```

To reinstall the Python SDK into this environment:

```bash
CYCLONEDDS_HOME=/home/azthor/opt/cyclonedds \
  uv pip install --python .venv_sim/bin/python \
  -e external_dependencies/unitree_sdk2_python
```

The upstream `install_mujoco_sim.sh` deletes and recreates `.venv_sim`, so it
is not needed for normal launches. The upstream `deploy.sh` additionally
checks for Clang and runs system setup; the local launchers use the verified
GCC-built binary directly.

Logs, installed dependency snapshots and model SHA-256 checksums are saved in
`.local/sonic-v1.1/`. These are local installation artifacts.

References: [repository](https://github.com/AlphaZ-Ai/GR00T-WholeBodyControl),
[deployment guide](docs/source/getting_started/installation_deploy.md),
[V1.1 models](docs/source/getting_started/download_models.md),
[simulation quick start](docs/source/getting_started/quickstart.md).
