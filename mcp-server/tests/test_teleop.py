import asyncio
import json

import websockets

from ml3_mcp import teleop


def test_sanitize_axis():
    assert teleop._sanitize_axis(2.0) == 1.0
    assert teleop._sanitize_axis(-5.0) == -1.0
    assert teleop._sanitize_axis(float("nan")) == 0.0
    assert teleop._sanitize_axis("bad") == 0.0
    assert teleop._sanitize_axis(0.3) == 0.3


async def _serve_capturing(received):
    async def handler(ws, *args):
        async for msg in ws:
            received.append(json.loads(msg))

    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, f"ws://127.0.0.1:{port}"


async def test_drive_for_streams_then_stops():
    received: list = []
    server, url = await _serve_capturing(received)
    try:
        result = await teleop.drive_for(
            url, 1.0, 0.0, 0.3, speed_scale=0.5, max_duration_s=3.0, rate=20.0
        )
        await asyncio.sleep(0.1)
    finally:
        server.close()
        await server.wait_closed()

    assert result["vx"] == 0.5  # 1.0 * speed_scale
    assert result["wz"] == 0.0
    assert result["ticks"] >= 4
    assert received[0] == {"vx": 0.5, "wz": 0.0}
    assert received[-1] == {"vx": 0.0, "wz": 0.0}  # always ends with a stop


async def test_drive_duration_capped():
    received: list = []
    server, url = await _serve_capturing(received)
    try:
        result = await teleop.drive_for(
            url, 0.5, 0.0, 99.0, max_duration_s=0.2, rate=20.0
        )
        await asyncio.sleep(0.05)
    finally:
        server.close()
        await server.wait_closed()
    assert result["duration_s"] == 0.2


async def test_stop_sends_zero():
    received: list = []
    server, url = await _serve_capturing(received)
    try:
        await teleop.stop(url)
        await asyncio.sleep(0.05)
    finally:
        server.close()
        await server.wait_closed()
    assert received == [{"vx": 0.0, "wz": 0.0}]
