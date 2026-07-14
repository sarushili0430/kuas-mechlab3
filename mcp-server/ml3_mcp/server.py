"""FastMCP (stdio) server exposing the ML3 robot's control / camera / recording
as tools for a local Claude. No authentication — intended for LAN-local use.

Config comes from environment variables (see config.py): ML3_HOST, ML3_WS_PORT,
ML3_CAM_PORT, ML3_REC_PORT, ML3_SPEED_SCALE, ML3_MAX_DURATION_S."""

from mcp.server.fastmcp import FastMCP, Image

from . import camera, record, teleop
from .config import CAMERA_TOPICS, load_config

CONFIG = load_config()
mcp = FastMCP("kuas-mechlab3-robot")


@mcp.tool()
async def drive(vx: float, wz: float, duration_s: float = 0.5) -> str:
    """Drive the robot for a bounded time, then automatically stop.

    Args:
        vx: Forward/back speed, normalized -1..1 (positive = forward).
        wz: Turn rate, normalized -1..1 (positive = turn left / counter-clockwise).
        duration_s: Seconds to hold the command before auto-stopping (capped by
            ML3_MAX_DURATION_S).

    The robot returns NO acknowledgement of motion. Move in short bursts and call
    capture_camera() before and after to confirm what actually happened.
    """
    result = await teleop.drive_for(
        CONFIG.ws_url,
        vx,
        wz,
        duration_s,
        speed_scale=CONFIG.speed_scale,
        max_duration_s=CONFIG.max_duration_s,
    )
    return (
        f"Sent vx={result['vx']:.3f}, wz={result['wz']:.3f} for "
        f"{result['duration_s']:.2f}s (~{result['ticks']} frames at 20Hz), then stopped. "
        f"speed_scale={CONFIG.speed_scale}. No motion ack exists — use capture_camera to verify."
    )


@mcp.tool()
async def stop() -> str:
    """Immediately stop the robot (send zero velocity)."""
    await teleop.stop(CONFIG.ws_url)
    return "Stop sent (vx=0, wz=0)."


@mcp.tool()
async def capture_camera(which: str = "front") -> Image:
    """Capture one still frame from a robot camera so you can see what it sees.

    Args:
        which: "front" (default) or "rear".
    """
    key = (which or "front").strip().lower()
    if key not in CAMERA_TOPICS:
        raise ValueError(f"unknown camera {which!r}; use 'front' or 'rear'")
    jpeg = await camera.fetch_frame(CONFIG.stream_url(CAMERA_TOPICS[key]))
    return Image(data=jpeg, format="jpeg")


@mcp.tool()
async def record_status() -> dict:
    """Get the imitation-learning recording status."""
    return await record.status(CONFIG.record_url("/record/status"))


@mcp.tool()
async def record_start(
    route: str | None = None,
    operator: str | None = None,
    rear: bool | None = None,
    state: bool | None = None,
) -> dict:
    """Start recording a dataset episode (rosbag). If a recording is already
    running the server returns an 'already_recording' error with HTTP 409 (see
    the '_http_status' field)."""
    return await record.start(
        CONFIG.record_url("/record/start"),
        route=route,
        operator=operator,
        rear=rear,
        state=state,
    )


@mcp.tool()
async def record_stop(label: str | None = None, notes: str | None = None) -> dict:
    """Stop and save the current recording. label: 'success' or 'failure'
    (canonicalized server-side)."""
    return await record.stop(
        CONFIG.record_url("/record/stop"), label=label, notes=notes
    )


@mcp.tool()
async def record_discard() -> dict:
    """Stop and discard (delete) the current recording episode."""
    return await record.discard(CONFIG.record_url("/record/discard"))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
