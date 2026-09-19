"""Torch-free Isaac-GR00T ``PolicyClient`` for the robot-side inference machine.

``gr00t.policy.server_client.PolicyClient`` is a thin ZMQ REQ client, but importing it
pulls ``gr00t.policy`` -> ``gr00t_policy`` -> torch/transformers, i.e. the whole model
stack, which the Thor does not need (the PolicyServer runs on the GPU box). This module
re-implements the client and its ``MsgSerializer`` wire format (msgpack + msgpack_numpy,
``allow_pickle=False``) from Isaac-GR00T ``gr00t/policy/server_client.py`` (Apache-2.0,
NVIDIA) with only numpy/zmq/msgpack dependencies. ``run_vla_inference.py`` uses the
upstream client when ``gr00t`` is importable and falls back to this one otherwise.
"""
from __future__ import annotations

import functools
import io
import json
from typing import Any

import msgpack
import msgpack_numpy as mnp
import numpy as np
import zmq


class MsgSerializer:
    @staticmethod
    def to_bytes(data: Any) -> bytes:
        return msgpack.packb(data, default=MsgSerializer._safe_encode)

    @staticmethod
    def from_bytes(data: bytes) -> Any:
        return msgpack.unpackb(data, object_hook=MsgSerializer._safe_decode, raw=False)

    @staticmethod
    def _safe_encode(obj):
        if isinstance(obj, np.ndarray) and obj.dtype.kind == "O":
            raise TypeError(f"Refusing to encode object-dtype ndarray (shape={obj.shape})")
        return mnp.encode(obj)

    @staticmethod
    def _safe_decode(obj):
        if isinstance(obj, dict):
            marker = obj.get("__ndarray_class__", obj.get(b"__ndarray_class__"))
            if marker:
                payload = obj.get("as_npy", obj.get(b"as_npy"))
                if payload is None:
                    raise ValueError("Malformed ndarray payload: 'as_npy' missing")
                return np.load(io.BytesIO(payload), allow_pickle=False)
            nd_val = obj.get(b"nd", obj.get("nd"))
            kind_val = obj.get(b"kind", obj.get("kind"))
            if nd_val and kind_val in (b"O", "O"):
                raise ValueError("Refusing to decode object-dtype ndarray payload")
            # ModalityConfig payloads come back as plain dicts (no gr00t dataclass here).
            for key in ("__ModalityConfig__", b"__ModalityConfig__"):
                if key in obj:
                    payload = obj.get("as_json", obj.get(b"as_json"))
                    if isinstance(payload, bytes):
                        payload = payload.decode()
                    return json.loads(payload) if isinstance(payload, str) else payload
        return mnp.decode(obj)


class PolicyClient:
    """ZMQ REQ client speaking the Isaac-GR00T PolicyServer protocol."""

    def __init__(self, host: str = "localhost", port: int = 5555, timeout_ms: int = 15000,
                 api_token: str | None = None, strict: bool = False):
        self.strict = strict
        self._closed = False
        self.context = zmq.Context()
        self.host, self.port, self.timeout_ms, self.api_token = host, port, timeout_ms, api_token
        self._init_socket()

    def _init_socket(self):
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        self.socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.connect(f"tcp://{self.host}:{self.port}")

    def ping(self) -> bool:
        try:
            self.call_endpoint("ping", requires_input=False)
            return True
        except zmq.error.ZMQError:
            self._init_socket()
            return False

    def kill_server(self):
        self.call_endpoint("kill", requires_input=False)

    def call_endpoint(self, endpoint: str, data: dict | None = None, requires_input: bool = True) -> Any:
        request: dict = {"endpoint": endpoint}
        if requires_input:
            request["data"] = data
        if self.api_token:
            request["api_token"] = self.api_token
        try:
            self.socket.send(MsgSerializer.to_bytes(request))
            message = self.socket.recv()
        except zmq.error.Again:
            self.socket.close(linger=0)
            self._init_socket()
            raise
        if message == b"ERROR":
            raise RuntimeError("Server error. Make sure we are running the correct policy server.")
        response = MsgSerializer.from_bytes(message)
        if isinstance(response, dict) and "error" in response:
            raise RuntimeError(f"Server error: {response['error']}")
        return response

    def get_action(self, observation: dict[str, Any], options: dict[str, Any] | None = None):
        response = self.call_endpoint("get_action", {"observation": observation, "options": options})
        return tuple(response)

    def reset(self, options: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.call_endpoint("reset", {"options": options})

    def get_modality_config(self):
        return self.call_endpoint("get_modality_config", requires_input=False)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.socket.close(linger=0)
            self.context.term()
        except Exception:
            pass
