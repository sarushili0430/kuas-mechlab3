"""ROS2 teleop viewer: subscribe to camera topics and serve them over HTTP.

This is the consumer side of the webcams. It subscribes to one or more
sensor_msgs/CompressedImage topics (the front/rear cameras by default, already
JPEG-encoded at the source) and relays the latest frame of each as MJPEG
(multipart/x-mixed-replace) so a remote teleop operator can watch both cameras
in a browser while driving.

Responsibility split: the multipart byte framing lives in ``mjpeg`` (pure,
pytest) and this node owns the ROS subscriptions plus the threaded HTTP server.
It does no image processing -- the camera nodes encode -- so it stays cheap on a
Raspberry Pi. For a batteries-included alternative, the ROS ``web_video_server``
package serves the same topics without this node.
"""

import select
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import parse_qs, urlparse

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage

from kuas_mechlab3.camera import mjpeg


class FrameStore:
    """Thread-safe holder for the latest JPEG bytes of each topic."""

    def __init__(self) -> None:
        """Start empty; frames arrive on the ROS thread, leave on HTTP threads."""
        self._lock = threading.Lock()
        self._frames: dict[str, bytes] = {}

    def put(self, topic: str, jpeg: bytes) -> None:
        """Replace the latest frame for ``topic`` (called from the ROS thread)."""
        with self._lock:
            self._frames[topic] = jpeg

    def get(self, topic: str) -> bytes | None:
        """Return the latest frame for ``topic``, or None if none yet."""
        with self._lock:
            return self._frames.get(topic)


class _Handler(BaseHTTPRequestHandler):
    """Serve an index page and a per-topic MJPEG stream from the FrameStore."""

    def log_message(self, format: str, *args: object) -> None:
        """Silence the default stderr access log; ROS logging covers lifecycle."""

    def do_GET(self) -> None:
        """Route "/" to the index page and "/stream?topic=.." to a video stream."""
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_index()
        elif parsed.path == "/stream":
            topic = parse_qs(parsed.query).get("topic", [""])[0]
            self._serve_stream(topic)
        else:
            self.send_error(404)

    def _serve_index(self) -> None:
        """Send the landing page listing every streamed camera."""
        server = cast(_StreamServer, self.server)
        body = mjpeg.index_html(server.topics).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_stream(self, topic: str) -> None:
        """Stream the latest JPEG of ``topic`` as multipart/x-mixed-replace."""
        server = cast(_StreamServer, self.server)
        if topic not in server.topics:
            self.send_error(404, "unknown topic")
            return
        try:
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", mjpeg.content_type())
            self.end_headers()
            period = 1.0 / server.stream_fps
            while not server.stop.is_set() and rclpy.ok():
                if self._client_gone():
                    break
                jpeg = server.store.get(topic)
                if jpeg is not None:
                    self.wfile.write(mjpeg.mjpeg_part(jpeg))
                server.stop.wait(period)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client closed the stream; nothing to clean up

    def _client_gone(self) -> bool:
        """True once the client has closed the socket.

        A topic that never produces a frame never triggers a write, so a
        BrokenPipeError is never raised on disconnect and the streaming loop
        would otherwise spin forever after the browser has gone -- one leaked
        thread (and socket) per stalled stream. Peeking the socket lets a
        frameless stream end cleanly too.
        """
        sock = self.request
        try:
            readable, _, _ = select.select([sock], [], [], 0)
            if not readable:
                return False
            return bool(sock.recv(1, socket.MSG_PEEK) == b"")
        except OSError:
            return True


class _StreamServer(ThreadingHTTPServer):
    """ThreadingHTTPServer carrying the shared state the handler reads."""

    def __init__(
        self,
        address: tuple[str, int],
        store: FrameStore,
        topics: list[str],
        stream_fps: float,
        stop: threading.Event,
    ) -> None:
        """Bind the socket and stash the state handlers pull frames from."""
        super().__init__(address, _Handler)
        self.store = store
        self.topics = topics
        self.stream_fps = stream_fps
        self.stop = stop


class MjpegServerNode(Node):  # type: ignore[misc]
    """Subscribe to camera image topics and stream them over HTTP for teleop."""

    def __init__(self) -> None:
        """Declare parameters, subscribe to each topic, start the HTTP server."""
        super().__init__("mjpeg_server")

        self.declare_parameter(
            "topics",
            [
                "/front_camera/image_raw/compressed",
                "/rear_camera/image_raw/compressed",
            ],
        )
        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 8080)
        self.declare_parameter("stream_fps", 15.0)

        self._topics = [str(t) for t in self.get_parameter("topics").value]
        self._store = FrameStore()
        self._stop = threading.Event()

        # default-arg t=topic binds the loop variable per subscription callback.
        self._subs = [
            self.create_subscription(
                CompressedImage,
                topic,
                lambda msg, t=topic: self._on_image(t, msg),
                qos_profile_sensor_data,
            )
            for topic in self._topics
        ]

        host = str(self.get_parameter("host").value)
        port = int(self.get_parameter("port").value)
        stream_fps = float(self.get_parameter("stream_fps").value)
        self._httpd = _StreamServer(
            (host, port), self._store, self._topics, stream_fps, self._stop
        )
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

        self.get_logger().info(
            f"mjpeg_server up: http://{host}:{port}/ streaming {self._topics}"
        )

    def _on_image(self, topic: str, msg: CompressedImage) -> None:
        """Stash the incoming JPEG bytes for the HTTP handlers (no re-encode)."""
        self._store.put(topic, bytes(msg.data))

    def shutdown(self) -> None:
        """Stop the streaming loops and the HTTP server thread."""
        self._stop.set()
        self._httpd.shutdown()
        self._httpd.server_close()


def main(args: list[str] | None = None) -> None:
    """Spin the viewer, tearing down the HTTP server on any exit path."""
    rclpy.init(args=args)
    node = MjpegServerNode()
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
