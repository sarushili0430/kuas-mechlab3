"""Runtime configuration for the ML3 MCP server, sourced from environment
variables. Nothing in the robot repo supplies a host/IP, so we define our own
knobs here. All are optional and have LAN-friendly, safety-first defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

DEFAULT_HOST = "192.168.1.42"

# Camera topics the robot publishes (camera/mjpeg_server.py defaults).
CAMERA_TOPICS = {
    "front": "/front_camera/image_raw/compressed",
    "rear": "/rear_camera/image_raw/compressed",
}


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip() or default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    host: str = DEFAULT_HOST
    ws_port: int = 9001
    cam_port: int = 8080
    rec_port: int = 9002
    speed_scale: float = 0.5  # global governor applied to every drive() axis
    max_duration_s: float = 3.0  # hard cap on how long one drive() command runs

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.ws_port}"

    def stream_url(self, topic: str) -> str:
        return f"http://{self.host}:{self.cam_port}/stream?topic={quote(topic, safe='')}"

    def record_url(self, path: str) -> str:
        return f"http://{self.host}:{self.rec_port}{path}"


def load_config() -> Config:
    return Config(
        host=_env_str("ML3_HOST", DEFAULT_HOST),
        ws_port=_env_int("ML3_WS_PORT", 9001),
        cam_port=_env_int("ML3_CAM_PORT", 8080),
        rec_port=_env_int("ML3_REC_PORT", 9002),
        speed_scale=clamp(_env_float("ML3_SPEED_SCALE", 0.5), 0.0, 1.0),
        max_duration_s=max(0.1, _env_float("ML3_MAX_DURATION_S", 3.0)),
    )
