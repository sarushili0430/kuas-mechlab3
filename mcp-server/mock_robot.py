"""In-process mock of the ML3 robot's three channels — teleop WS (9001), camera
MJPEG (8080), recording HTTP (9002) — for exercising the MCP server without any
hardware.

Run directly to serve on the default ports (Ctrl-C to stop):

    python mock_robot.py

Or import ``MockRobot`` in tests. Ports of 0 are NOT auto-resolved here; pass
explicit ports (the test suite picks free ones)."""
from __future__ import annotations

import asyncio
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websockets

# A tiny but valid 1x1 JPEG, so capture_camera() returns real decodable bytes.
_TINY_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
    "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
    "AAAAAAAAAAAAAAAAAAAAAv/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AfwD/2Q=="
)


def _mjpeg_part(jpeg: bytes) -> bytes:
    return (
        b"--ml3frame\r\n"
        b"Content-Type: image/jpeg\r\n"
        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n"
    )


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _CamHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (stdlib naming)
        if self.path.startswith("/stream"):
            self.send_response(200)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=ml3frame"
            )
            self.end_headers()
            part = _mjpeg_part(_TINY_JPEG)
            try:
                for _ in range(50):  # enough for a client to grab one frame
                    self.wfile.write(part)
                    self.wfile.flush()
                    time.sleep(0.05)
            except (BrokenPipeError, ConnectionResetError, ValueError, OSError):
                pass
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):  # silence
        pass


class _RecHandler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        robot: MockRobot = self.server.robot  # type: ignore[attr-defined]
        if self.path == "/record/status":
            self._send_json(200, robot.status_payload())
        else:
            self._send_json(404, {"recording": None, "error": "not_found"})

    def do_POST(self):  # noqa: N802
        robot: MockRobot = self.server.robot  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        if self.path == "/record/start":
            if robot.recording:
                self._send_json(409, {"recording": None, "error": "already_recording"})
            else:
                robot.recording = True
                self._send_json(200, robot.status_payload())
        elif self.path == "/record/stop":
            if not robot.recording:
                self._send_json(409, {"recording": None, "error": "not_recording"})
            else:
                robot.recording = False
                idx = robot.index
                robot.index += 1
                self._send_json(
                    200,
                    {
                        "recording": False,
                        "saved": f"episode_{idx:04d}",
                        "index": idx,
                        "label": body.get("label") or "success",
                        "notes": body.get("notes", ""),
                        "duration_s": 1.0,
                    },
                )
        elif self.path == "/record/discard":
            robot.recording = False
            self._send_json(
                200,
                {
                    "recording": False,
                    "discarded": True,
                    "episode": f"episode_{robot.index:04d}",
                    "index": robot.index,
                },
            )
        else:
            self._send_json(404, {"recording": None, "error": "not_found"})

    def log_message(self, *args):  # silence
        pass


class MockRobot:
    def __init__(
        self,
        host: str = "127.0.0.1",
        ws_port: int = 9001,
        cam_port: int = 8080,
        rec_port: int = 9002,
    ):
        self.host = host
        self.ws_port = ws_port
        self.cam_port = cam_port
        self.rec_port = rec_port
        self.commands: list[tuple[float, float]] = []  # every {vx,wz} received on WS
        self.recording = False
        self.index = 1
        self._threads: list[threading.Thread] = []
        self._cam_srv: _HTTPServer | None = None
        self._rec_srv: _HTTPServer | None = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._ws_server = None
        self._ready = threading.Event()

    def status_payload(self) -> dict:
        return {
            "recording": self.recording,
            "index": self.index,
            "episode": (f"episode_{self.index:04d}" if self.recording else None),
            "started_at": None,
            "route": "route_a",
            "operator": "mock",
        }

    async def _ws_handler(self, websocket, *args):
        async for message in websocket:
            text = (
                message.decode()
                if isinstance(message, (bytes, bytearray))
                else message
            )
            try:
                data = json.loads(text)
                self.commands.append((float(data["vx"]), float(data["wz"])))
            except Exception:
                pass

    def _run_ws(self):
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)
        self._ws_server = self._ws_loop.run_until_complete(
            websockets.serve(self._ws_handler, self.host, self.ws_port)
        )
        self._ready.set()
        self._ws_loop.run_forever()
        self._ws_server.close()
        self._ws_loop.run_until_complete(self._ws_server.wait_closed())
        self._ws_loop.close()

    def start(self) -> "MockRobot":
        t_ws = threading.Thread(target=self._run_ws, daemon=True)
        t_ws.start()
        self._threads.append(t_ws)
        self._ready.wait(timeout=5)

        self._cam_srv = _HTTPServer((self.host, self.cam_port), _CamHandler)
        t_cam = threading.Thread(target=self._cam_srv.serve_forever, daemon=True)
        t_cam.start()
        self._threads.append(t_cam)

        self._rec_srv = _HTTPServer((self.host, self.rec_port), _RecHandler)
        self._rec_srv.robot = self  # type: ignore[attr-defined]
        t_rec = threading.Thread(target=self._rec_srv.serve_forever, daemon=True)
        t_rec.start()
        self._threads.append(t_rec)
        return self

    def stop(self):
        if self._cam_srv:
            self._cam_srv.shutdown()
            self._cam_srv.server_close()
        if self._rec_srv:
            self._rec_srv.shutdown()
            self._rec_srv.server_close()
        if self._ws_loop:
            self._ws_loop.call_soon_threadsafe(self._ws_loop.stop)
        for t in self._threads:
            t.join(timeout=2)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()


def main():
    robot = MockRobot().start()
    front = "/front_camera/image_raw/compressed"
    print(
        "Mock ML3 robot running:\n"
        f"  teleop  ws://{robot.host}:{robot.ws_port}\n"
        f"  camera  http://{robot.host}:{robot.cam_port}/stream?topic={front}\n"
        f"  record  http://{robot.host}:{robot.rec_port}/record/status\n"
        "Ctrl-C to stop."
    )
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        robot.stop()


if __name__ == "__main__":
    main()
