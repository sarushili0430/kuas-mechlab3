"""ROS2 remote-teleop bridge: WebSocket commands in, cmd_vel Twist out.

The network counterpart of ``teleop_keyboard``. A remote operator (a browser or
the bundled ``teleop_ws_client``) sends small JSON commands
``{"vx": .., "wz": ..}`` with normalised axes in [-1, 1]; this node maps each to
a geometry_msgs/Twist and publishes it on cmd_vel at a steady rate, exactly like
``teleop_keyboard``, so ``kinematics`` / ``serial_link`` / ``mbed_driver`` (the
watchdog included) stay untouched -- this is just another cmd_vel publisher.

Responsibility split: the JSON parsing / scaling lives in ``teleop_command``
(pure, pytest) and the WebSocket wire protocol in the ``websockets`` library, so
this node owns only the ROS publishing and the threaded server lifecycle. The
server runs an asyncio loop on a background daemon thread (mirroring how
``mjpeg_server`` runs its HTTP server off-thread); inbound commands are handed to
the ROS side through a lock-guarded ``CommandStore`` and published from the ROS
timer alone -- the asyncio thread never touches rclpy.

Three-layer failsafe, each independent:
  1. socket close -- a dropped client zeroes the very next published Twist
  2. hold_timeout -- a connected-but-silent client decays to a zero Twist
  3. mbed_driver  -- the driver's own cmd_timeout watchdog (unchanged)
"""

import asyncio
import threading
import time
from typing import Any

import rclpy
import websockets
from geometry_msgs.msg import Twist
from rclpy.node import Node

from kuas_mechlab3.drive.teleop_command import command_to_twist, parse_command


class CommandStore:
    """Thread-safe holder for the latest normalised command and liveness.

    Written from the WebSocket (asyncio) thread, read from the ROS timer; the
    lock keeps the (vx, wz, timestamp, client-count) tuple consistent across the
    two -- the same hand-off pattern as ``mjpeg_server.FrameStore``.
    """

    def __init__(self) -> None:
        """Start stopped: no clients and a stale timestamp (so age is huge)."""
        self._lock = threading.Lock()
        self._vx = 0.0
        self._wz = 0.0
        self._stamp = 0.0
        self._clients = 0

    def set_command(self, vx: float, wz: float) -> None:
        """Replace the latest command and re-stamp it (WebSocket thread)."""
        with self._lock:
            self._vx = vx
            self._wz = wz
            self._stamp = time.monotonic()

    def add_client(self) -> None:
        """Register a newly connected client."""
        with self._lock:
            self._clients += 1

    def remove_client(self) -> None:
        """Deregister a disconnected client (floors at zero)."""
        with self._lock:
            self._clients = max(0, self._clients - 1)

    def snapshot(self) -> tuple[float, float, float, bool]:
        """Return (vx, wz, age_seconds, has_client) atomically (ROS thread)."""
        with self._lock:
            age = time.monotonic() - self._stamp
            return self._vx, self._wz, age, self._clients > 0


class _CommandWsServer:
    """Run a ``websockets`` server on a background thread into a CommandStore.

    The asyncio loop lives on its own daemon thread; the ROS side only calls
    ``start()`` / ``shutdown()``. Inbound JSON is parsed by ``parse_command`` and
    the latest value dropped into the store -- this server never imports or
    touches rclpy.
    """

    def __init__(
        self,
        host: str,
        port: int,
        store: CommandStore,
        ping_interval: float,
        ping_timeout: float,
    ) -> None:
        """Create the loop and worker thread (not started until ``start()``)."""
        self._host = host
        self._port = port
        self._store = store
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._loop = asyncio.new_event_loop()
        self._server: Any = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        """Start serving on the background thread."""
        self._thread.start()

    def _run(self) -> None:
        """Thread body: serve until the loop is stopped, then close cleanly."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_server())
        self._loop.run_forever()
        self._loop.run_until_complete(self._stop_server())
        self._loop.close()

    async def _start_server(self) -> None:
        """Bind the WebSocket listener with built-in ping/pong keepalive."""
        self._server = await websockets.serve(
            self._handler,
            self._host,
            self._port,
            ping_interval=self._ping_interval,
            ping_timeout=self._ping_timeout,
        )

    async def _stop_server(self) -> None:
        """Stop accepting and drain open connections."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, websocket: Any, _path: Any = None) -> None:
        """Feed one client's commands into the store until it disconnects.

        The ``finally`` is the deadman: when the socket drops (close or a missed
        ping/pong) the client count falls and the ROS timer publishes zero.
        ``_path`` keeps the legacy two-argument handler signature (websockets
        10.x, the Humble apt build) working while tolerating newer one-arg calls.
        """
        self._store.add_client()
        try:
            async for message in websocket:
                text = message.decode() if isinstance(message, bytes) else message
                parsed = parse_command(text)
                if parsed is not None:
                    self._store.set_command(*parsed)
        except websockets.ConnectionClosed:
            pass
        finally:
            self._store.remove_client()

    def shutdown(self) -> None:
        """Stop the loop from the caller's thread and join the worker."""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=2.0)


class TeleopServer(Node):  # type: ignore[misc]
    """Bridge a WebSocket command stream onto the cmd_vel topic."""

    def __init__(self) -> None:
        """Declare parameters, open the WebSocket server, start the timer."""
        super().__init__("teleop_server")

        self.declare_parameter("host", "0.0.0.0")
        self.declare_parameter("port", 9001)
        self.declare_parameter("publish_rate", 20.0)
        self.declare_parameter("hold_timeout", 0.4)
        self.declare_parameter("max_linear", 0.5)
        self.declare_parameter("max_angular", 2.0)
        self.declare_parameter("deadzone", 0.05)
        self.declare_parameter("ping_interval", 5.0)
        self.declare_parameter("ping_timeout", 5.0)

        self._max_linear = float(self.get_parameter("max_linear").value)
        self._max_angular = float(self.get_parameter("max_angular").value)
        self._deadzone = float(self.get_parameter("deadzone").value)
        self._hold_timeout = float(self.get_parameter("hold_timeout").value)

        host = str(self.get_parameter("host").value)
        port = int(self.get_parameter("port").value)
        ping_interval = float(self.get_parameter("ping_interval").value)
        ping_timeout = float(self.get_parameter("ping_timeout").value)

        self._store = CommandStore()
        self._pub = self.create_publisher(Twist, "cmd_vel", 10)

        self._server = _CommandWsServer(
            host, port, self._store, ping_interval, ping_timeout
        )
        self._server.start()

        rate = float(self.get_parameter("publish_rate").value)
        self._timer = self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info(f"teleop_server up: ws://{host}:{port} -> cmd_vel")

    def _tick(self) -> None:
        """Publish the latest command as a Twist, or zero if stale / unmanned."""
        vx_norm, wz_norm, age, has_client = self._store.snapshot()
        twist = Twist()
        if has_client and age <= self._hold_timeout:
            vx, wz = command_to_twist(
                vx_norm, wz_norm, self._max_linear, self._max_angular, self._deadzone
            )
            twist.linear.x = vx
            twist.angular.z = wz
        self._pub.publish(twist)

    def shutdown(self) -> None:
        """Stop the server and send a final explicit zero Twist."""
        self._server.shutdown()
        self._pub.publish(Twist())


def main(args: list[str] | None = None) -> None:
    """Spin the bridge, guaranteeing server teardown and a stop on any exit."""
    rclpy.init(args=args)
    node = TeleopServer()
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
