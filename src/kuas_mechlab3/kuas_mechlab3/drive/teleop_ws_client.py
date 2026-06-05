"""Dev WebSocket teleop client: hold WASD to drive teleop_server over a socket.

The operator-side counterpart of ``teleop_keyboard``. It reads the keyboard in
cbreak mode and streams ``{"vx": .., "wz": ..}`` (normalised axes in [-1, 1]) to
a ``teleop_server`` WebSocket at a steady rate; releasing a key lets the command
decay to zero and exit sends a final stop. This is pure operator-side tooling --
it imports neither rclpy nor the ROS message types, so it runs on a laptop with
only the ``websockets`` package installed (no sourced ROS2). For a one-off check
without this client, pipe a single frame with websocat instead:

    echo '{"vx":0.5,"wz":0.0}' | websocat ws://<pi>:9001
"""

import argparse
import asyncio
import contextlib
import json
import select
import sys
import termios
import time
import tty

import websockets

BANNER = """\
============================================
   ML3 Remote WS Teleop  (-> teleop_server)
============================================
   HOLD a key to move -- release to stop:
   w = forward        s = backward
   a = turn left      d = turn right
   q = stop           Ctrl+C = quit (auto-stops)
============================================"""


def _read_key() -> str:
    """Return one buffered keystroke without blocking, or '' if none."""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return ""


def _key_to_axes(key: str, linear: float, angular: float) -> tuple[float, float] | None:
    """Map one WASD keystroke to normalised (vx, wz); None if it is not a key."""
    if key == "w":
        return linear, 0.0
    if key == "s":
        return -linear, 0.0
    if key == "a":
        return 0.0, angular
    if key == "d":
        return 0.0, -angular
    if key == "q":
        return 0.0, 0.0
    return None


async def _drive(
    url: str, linear: float, angular: float, rate: float, hold_timeout: float
) -> None:
    """Connect, then stream the held-key command until interrupted."""
    period = 1.0 / rate
    async with websockets.connect(url) as ws:
        target = (0.0, 0.0)
        last_key_t = time.monotonic()
        try:
            while True:
                mapped = _key_to_axes(_read_key(), linear, angular)
                if mapped is not None:
                    target = mapped
                    last_key_t = time.monotonic()
                if time.monotonic() - last_key_t > hold_timeout:
                    target = (0.0, 0.0)
                await ws.send(json.dumps({"vx": target[0], "wz": target[1]}))
                await asyncio.sleep(period)
        finally:
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"vx": 0.0, "wz": 0.0}))


def main() -> None:
    """Parse args, put the terminal in cbreak mode, and run the send loop."""
    parser = argparse.ArgumentParser(
        description="ML3 remote WebSocket teleop client (WASD -> teleop_server)"
    )
    parser.add_argument(
        "--url", default="ws://localhost:9001", help="teleop_server WebSocket URL"
    )
    parser.add_argument(
        "--linear", type=float, default=1.0, help="normalised vx for w/s [0..1]"
    )
    parser.add_argument(
        "--angular", type=float, default=1.0, help="normalised wz for a/d [0..1]"
    )
    parser.add_argument("--rate", type=float, default=20.0, help="send rate [Hz]")
    parser.add_argument(
        "--hold-timeout", type=float, default=0.4, help="release-to-zero decay [s]"
    )
    args = parser.parse_args()

    print(BANNER, flush=True)
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        asyncio.run(
            _drive(args.url, args.linear, args.angular, args.rate, args.hold_timeout)
        )
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        print(f"\nconnection failed: {exc}", file=sys.stderr)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


if __name__ == "__main__":
    main()
