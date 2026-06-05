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
