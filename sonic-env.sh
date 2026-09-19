#!/usr/bin/env bash
# Source this file to use this checkout's Thor deployment dependencies.
export SONIC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TensorRT_ROOT=/usr
export CUDAToolkit_ROOT=/usr/local/cuda
export CUDA_HOME="$CUDAToolkit_ROOT"
export CYCLONEDDS_HOME=/home/azthor/opt/cyclonedds
export onnxruntime_ROOT=/home/azthor/opt/onnxruntime
export PATH="$SONIC_ROOT/.local/sonic-v1.1/bin:$CUDAToolkit_ROOT/bin:$PATH"
export CMAKE_PREFIX_PATH="$onnxruntime_ROOT:${CMAKE_PREFIX_PATH:-}"
export CPATH="/home/azthor/opt/include:${CPATH:-}"
export LD_LIBRARY_PATH="$onnxruntime_ROOT/lib:$CUDAToolkit_ROOT/lib64:${LD_LIBRARY_PATH:-}"
