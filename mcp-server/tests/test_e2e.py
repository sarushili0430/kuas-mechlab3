"""End-to-end tests: the real client modules against the in-process MockRobot
(real sockets on all three channels)."""

import asyncio

from ml3_mcp import camera, record, teleop
from ml3_mcp.config import CAMERA_TOPICS, Config


def _config(mock_robot) -> Config:
    return Config(
        host=mock_robot.host,
        ws_port=mock_robot.ws_port,
        cam_port=mock_robot.cam_port,
        rec_port=mock_robot.rec_port,
        speed_scale=0.5,
        max_duration_s=3.0,
    )


async def test_drive_reaches_mock(mock_robot):
    cfg = _config(mock_robot)
    result = await teleop.drive_for(
        cfg.ws_url,
        1.0,
        0.0,
        0.25,
        speed_scale=cfg.speed_scale,
        max_duration_s=cfg.max_duration_s,
    )
    await asyncio.sleep(0.15)
    assert result["ticks"] >= 3
    assert mock_robot.commands, "mock received no commands"
    assert mock_robot.commands[0] == (0.5, 0.0)  # scaled by speed_scale
    assert mock_robot.commands[-1] == (0.0, 0.0)  # final stop


async def test_stop_reaches_mock(mock_robot):
    cfg = _config(mock_robot)
    await teleop.stop(cfg.ws_url)
    await asyncio.sleep(0.1)
    assert mock_robot.commands[-1] == (0.0, 0.0)


async def test_capture_camera(mock_robot):
    cfg = _config(mock_robot)
    jpeg = await camera.fetch_frame(cfg.stream_url(CAMERA_TOPICS["front"]))
    assert jpeg[:2] == b"\xff\xd8"  # JPEG start-of-image
    assert jpeg[-2:] == b"\xff\xd9"  # JPEG end-of-image


async def test_record_cycle(mock_robot):
    cfg = _config(mock_robot)
    assert (await record.status(cfg.record_url("/record/status")))["recording"] is False

    started = await record.start(
        cfg.record_url("/record/start"), route="r", operator="me"
    )
    assert started["recording"] is True

    dup = await record.start(cfg.record_url("/record/start"))
    assert dup["_http_status"] == 409
    assert dup["error"] == "already_recording"

    stopped = await record.stop(cfg.record_url("/record/stop"), label="success")
    assert stopped["recording"] is False
    assert stopped["saved"]
