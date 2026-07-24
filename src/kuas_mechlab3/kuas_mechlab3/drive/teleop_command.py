"""Pure command translation for remote teleop (no ROS / websocket deps).

Single owner of the WebSocket command format: a small JSON object with
normalised axes, parsed into (vx, wz) in [-1, 1], then scaled to a physical
(vx[m/s], wz[rad/s]) pair against the robot's configured maxima. Keeping these
as string<->number functions lets the standalone pytest job cover them;
``teleop_server`` owns the socket, the ROS publishing, and the threading on top
of this module.
"""

import json
import math

from kuas_mechlab3.utils import clamp


def parse_command(raw: str) -> tuple[float, float] | None:
    """Parse one ``{"vx": .., "wz": ..}`` message into normalised (vx, wz).

    vx / wz are the normalised axes in [-1, 1] (clamping is left to
    ``command_to_twist``). Returns None for anything that is not a well-formed
    command -- bad JSON, a non-object, a missing key, or a non-numeric or
    non-finite value -- so the caller can simply ignore it (mirrors
    ``parse_telemetry``).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        vx = float(data["vx"])
        wz = float(data["wz"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(vx) and math.isfinite(wz)):
        return None
    return vx, wz


def parse_servo_command(raw: str) -> tuple[float, float] | None:
    """Parse one ``{"servo": [shoulder_deg, elbow_deg]}`` message into (sh, el).

    Returns None for anything that is not a well-formed servo command -- bad JSON,
    a non-object, a missing "servo" key, a value that is not a 2-element list, or a
    non-numeric / non-finite element -- so the caller can simply ignore it (mirrors
    ``parse_command``). Angle->pulse calibration + clamping live downstream in
    ``protocol.angle_to_us``; this only validates and extracts the pair.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "servo" not in data:
        return None
    servo = data["servo"]
    if not isinstance(servo, list) or len(servo) != 2:
        return None
    try:
        shoulder = float(servo[0])
        elbow = float(servo[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(shoulder) and math.isfinite(elbow)):
        return None
    return shoulder, elbow


def parse_led_command(raw: str) -> bool | None:
    """Parse one ``{"led": true|false}`` message into a bool, else None.

    Returns None for anything that is not a well-formed LED command -- bad JSON, a
    non-object, a missing "led" key, or a value that is not a bool or a 0|1 int --
    so the caller can simply ignore it (mirrors ``parse_command``).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "led" not in data:
        return None
    value = data["led"]
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def command_to_twist(
    vx_norm: float,
    wz_norm: float,
    max_linear: float,
    max_angular: float,
    deadzone: float = 0.0,
) -> tuple[float, float]:
    """Map normalised axes in [-1, 1] to a physical (vx[m/s], wz[rad/s]).

    Each axis is clamped to [-1, 1], zeroed if its magnitude is within
    ``deadzone`` (analog-stick noise / drift), then scaled by the matching
    maximum so full deflection commands max_linear / max_angular.
    """
    vx = clamp(vx_norm, -1.0, 1.0)
    wz = clamp(wz_norm, -1.0, 1.0)
    if abs(vx) < deadzone:
        vx = 0.0
    if abs(wz) < deadzone:
        wz = 0.0
    return vx * max_linear, wz * max_angular


def command_to_norm(vx_norm: float, wz_norm: float) -> tuple[float, float]:
    """Clamp the raw axes to [-1, 1] -- the normalised command as it crosses the
    WebSocket, before any physical scaling.

    This is the imitation-learning action label. A human operator and a future
    autonomous policy occupy the same slot (the WebSocket sender), so logging this
    value -- not the scaled cmd_vel -- keeps the training target in the model's own
    output space (what it must emit) rather than in physical units. Deadzone is
    deliberately NOT applied: it is a downstream safety filter (``command_to_twist``)
    applied identically to human and policy commands, not part of the demonstrated
    intent, so train/inference stay symmetric.
    """
    return clamp(vx_norm, -1.0, 1.0), clamp(wz_norm, -1.0, 1.0)
