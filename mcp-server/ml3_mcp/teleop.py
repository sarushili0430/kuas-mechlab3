"""Thin async WebSocket client for the robot's teleop server (port 9001).

The robot expects a continuous ~20 Hz stream of JSON ``{"vx", "wz"}`` messages,
normalized to [-1, 1]. It is fire-and-forget with no acknowledgement, and it
zeroes motion if commands stop arriving (0.4 s hold timeout, plus a driver
watchdog). We therefore hold a command for a bounded duration and ALWAYS finish
with a stop, even on error."""

from __future__ import annotations

import asyncio
import json
import math

import websockets

STOP_PAYLOAD = json.dumps({"vx": 0.0, "wz": 0.0})


def _sanitize_axis(value: float) -> float:
    """Coerce to a finite float in [-1, 1]; anything invalid becomes 0.0."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(v):
        return 0.0
    return max(-1.0, min(1.0, v))


async def drive_for(
    url: str,
    vx: float,
    wz: float,
    duration_s: float,
    *,
    speed_scale: float = 1.0,
    max_duration_s: float = 3.0,
    rate: float = 20.0,
    connect_timeout: float = 5.0,
) -> dict:
    """Hold ``{vx, wz}`` for ``duration_s`` (capped at ``max_duration_s``),
    streaming at ~``rate`` Hz, then stop. Axes are clamped to [-1, 1] and scaled
    by ``speed_scale``. A final stop is always sent."""
    scale = max(0.0, min(1.0, speed_scale))
    vx = _sanitize_axis(vx) * scale
    wz = _sanitize_axis(wz) * scale
    duration_s = max(0.0, min(float(duration_s), max_duration_s))
    period = 1.0 / rate if rate > 0 else 0.05
    payload = json.dumps({"vx": vx, "wz": wz})
    ticks = 0

    async with websockets.connect(
        url, open_timeout=connect_timeout, close_timeout=2
    ) as ws:
        try:
            loop = asyncio.get_running_loop()
            start = loop.time()
            await ws.send(payload)
            ticks += 1
            while (loop.time() - start) < duration_s:
                await asyncio.sleep(period)
                await ws.send(payload)
                ticks += 1
        finally:
            try:
                await ws.send(STOP_PAYLOAD)
            except Exception:
                pass
    return {"vx": vx, "wz": wz, "duration_s": duration_s, "ticks": ticks}


async def stop(url: str, *, connect_timeout: float = 5.0) -> dict:
    """Send a single stop (zero velocity) command."""
    async with websockets.connect(
        url, open_timeout=connect_timeout, close_timeout=2
    ) as ws:
        await ws.send(STOP_PAYLOAD)
    return {"vx": 0.0, "wz": 0.0, "stopped": True}
