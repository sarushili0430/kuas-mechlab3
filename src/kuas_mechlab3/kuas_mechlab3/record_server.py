"""ROS2 node: an HTTP control API to flag imitation-learning episodes.

The remote counterpart of the interactive recorder ``scripts/record_episodes.py``.
A phone (the cockpit's REC button) POSTs tiny JSON requests to start / stop /
discard an episode and GETs the current status; this node drives ``ros2 bag
record`` accordingly so an operator can flag an episode's begin and end without a
Pi terminal. Recording stays a *separate concern* from driving: this is its own
node on its own port, so ``teleop_server`` remains publish-only (a recorded human
demo and a future autonomous policy occupy the same WebSocket slot untouched).

Responsibility split mirrors the other servers: the wire protocol (request
parsing / response payloads) lives in the pure ``record_control`` module, the bag
subprocess lifecycle in ``record_session`` (DI-testable), and the dataset schema
in ``recording``; this node owns only the HTTP surface and the threaded server
lifecycle. The HTTP server runs on a background daemon thread exactly like
``mjpeg_server`` -- the ROS side only wires parameters and tears it down on exit.

No auth (LAN-only, like the teleop WebSocket and the MJPEG stream). CORS is open
so the cockpit, served from a different origin (or ``file://``), can call it.
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast

import rclpy
from rclpy.node import Node

from kuas_mechlab3 import record_control
from kuas_mechlab3.record_session import (
    AlreadyRecording,
    NotRecording,
    RecordingSession,
)
from kuas_mechlab3.recording import default_topics

_MAX_BODY_BYTES = 64 * 1024  # a control request is tiny; cap to reject garbage


class _Handler(BaseHTTPRequestHandler):
    """Route the four control endpoints onto the shared RecordingSession."""

    def log_message(self, format: str, *args: object) -> None:
        """Silence the default stderr access log; ROS logging covers lifecycle."""

    def _session(self) -> RecordingSession:
        """The session carried by the server (shared across handler threads)."""
        return cast(_ControlServer, self.server).session

    def _send_json(self, code: int, payload: dict[str, Any]) -> None:
        """Write a JSON body with open-CORS headers."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        """Allow any LAN origin (incl. ``file://``) to call the API."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _read_body(self) -> str:
        """Read the request body as text (empty string if none / too large)."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return ""
        if length <= 0 or length > _MAX_BODY_BYTES:
            return ""
        return self.rfile.read(length).decode("utf-8", errors="replace")

    def do_OPTIONS(self) -> None:
        """Answer CORS preflight for the cockpit's POSTs."""
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Only ``/record/status`` is a GET; everything else is 404."""
        if self.path == record_control.STATUS_PATH:
            self._send_json(200, self._session().status())
        else:
            self._send_json(404, record_control.error_payload("not_found"))

    def do_POST(self) -> None:
        """Dispatch start / stop / discard; each maps a conflict to HTTP 409."""
        session = self._session()
        if self.path == record_control.START_PATH:
            opts = record_control.parse_start_request(self._read_body())
            topics = default_topics(
                include_rear=(
                    opts.include_rear if opts.include_rear is not None else True
                ),
                include_state=(
                    opts.include_state if opts.include_state is not None else True
                ),
            )
            try:
                payload = session.start(
                    route=opts.route, operator=opts.operator, topics=topics
                )
            except AlreadyRecording:
                self._send_json(409, record_control.error_payload("already_recording"))
                return
            self._send_json(200, payload)
        elif self.path == record_control.STOP_PATH:
            stop = record_control.parse_stop_request(self._read_body())
            try:
                payload = session.stop(label=stop.label, notes=stop.notes)
            except NotRecording:
                self._send_json(409, record_control.error_payload("not_recording"))
                return
            self._send_json(200, payload)
        elif self.path == record_control.DISCARD_PATH:
            try:
                payload = session.discard()
            except NotRecording:
                self._send_json(409, record_control.error_payload("not_recording"))
                return
            self._send_json(200, payload)
        else:
            self._send_json(404, record_control.error_payload("not_found"))


class _ControlServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying the RecordingSession the handlers drive."""

    def __init__(self, address: tuple[str, int], session: RecordingSession) -> None:
        """Bind the socket and stash the session shared across handler threads."""
        super().__init__(address, _Handler)
        self.session = session


class RecordServerNode(Node):  # type: ignore[misc]
    """Expose start / stop / discard / status of episode recording over HTTP."""

    def __init__(self) -> None:
        """Declare parameters, build the session, start the HTTP server."""
        super().__init__("record_server")

        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 9002)
        self.declare_parameter("out", "datasets/raw")
        self.declare_parameter("route", "route_a")
        self.declare_parameter("operator", "unknown")
        self.declare_parameter("storage", "sqlite3")
        self.declare_parameter("include_rear", True)
        self.declare_parameter("include_state", True)
        self.declare_parameter("start_index", 1)

        out_root = Path(str(self.get_parameter("out").value)).expanduser()
        out_root.mkdir(parents=True, exist_ok=True)
        topics = default_topics(
            include_rear=bool(self.get_parameter("include_rear").value),
            include_state=bool(self.get_parameter("include_state").value),
        )
        domain = os.environ.get("ROS_DOMAIN_ID")
        domain_id = int(domain) if domain and domain.isdigit() else None

        self._session = RecordingSession(
            out_root=out_root,
            route=str(self.get_parameter("route").value),
            operator=str(self.get_parameter("operator").value),
            topics=topics,
            storage=str(self.get_parameter("storage").value),
            start_index=int(self.get_parameter("start_index").value),
            ros_domain_id=domain_id,
        )

        host = str(self.get_parameter("host").value)
        port = int(self.get_parameter("port").value)
        self._httpd = _ControlServer((host, port), self._session)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

        self.get_logger().info(
            f"record_server up: http://{host}:{port}{record_control.STATUS_PATH}"
            f" -> {out_root}"
        )

    def shutdown(self) -> None:
        """Stop the HTTP server and save any in-flight episode as unlabeled."""
        self._httpd.shutdown()
        self._httpd.server_close()
        saved = self._session.finalize_unlabeled(notes="record_server shutdown")
        if saved is not None:
            self.get_logger().info(f"finalized in-flight episode: {saved['saved']}")


def main(args: list[str] | None = None) -> None:
    """Spin the control server, tearing down the HTTP server on any exit path."""
    rclpy.init(args=args)
    node = RecordServerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
