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

Alongside cmd_vel it also publishes the *normalised* command on ``cmd_norm``
(geometry_msgs/TwistStamped: vx in linear.x, wz in angular.z, both in [-1, 1]) --
the raw axes as they cross the WebSocket, stamped on the node clock so an offline
tool can pair each action with the camera frame in effect at that instant. This is
the action label for imitation-learning logs: a recorded human demonstration and a
future autonomous policy occupy the same WebSocket slot, so this topic is exactly
what the policy must learn to emit. It is publish-only -- recording is a separate
concern (see ``scripts/record_episodes.py``).
"""

import asyncio
import threading
import time
from typing import Any

import rclpy
import websockets
from geometry_msgs.msg import Twist, TwistStamped
from rclpy.node import Node
from std_msgs.msg import Bool, Float32MultiArray

from kuas_mechlab3.drive.teleop_command import (
    command_to_norm,
    command_to_twist,
    parse_command,
    parse_led_command,
    parse_servo_command,
)


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
        # Latched arm / LED commands: set on arrival, taken once by the ROS timer
        # then cleared (None = nothing pending). Unlike drive they are NOT decayed
        # on staleness -- the firmware holds the last servo pulse / LED state.
        self._servo: tuple[float, float] | None = None
        self._led: bool | None = None

    def set_command(self, vx: float, wz: float) -> None:
        """Replace the latest command and re-stamp it (WebSocket thread)."""
        with self._lock:
            self._vx = vx
            self._wz = wz
            self._stamp = time.monotonic()

    def set_servo(self, shoulder: float, elbow: float) -> None:
        """Latch a new arm command in degrees (WebSocket thread)."""
        with self._lock:
            self._servo = (shoulder, elbow)

    def set_led(self, on: bool) -> None:
        """Latch a new LED on/off command (WebSocket thread)."""
        with self._lock:
            self._led = on

    def take_servo(self) -> tuple[float, float] | None:
        """Return the pending arm command and clear it, else None (ROS thread)."""
        with self._lock:
            servo, self._servo = self._servo, None
            return servo

    def take_led(self) -> bool | None:
        """Return the pending LED command and clear it, else None (ROS thread)."""
        with self._lock:
            led, self._led = self._led, None
            return led

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
                # One socket carries three command shapes; the parsers are
                # mutually exclusive, so try each in turn (drive / arm / LED).
                drive = parse_command(text)
                if drive is not None:
                    self._store.set_command(*drive)
                    continue
                servo = parse_servo_command(text)
                if servo is not None:
                    self._store.set_servo(*servo)
                    continue
                led = parse_led_command(text)
                if led is not None:
                    self._store.set_led(led)
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
        # Normalised twin of cmd_vel for imitation-learning logs (the action a
        # policy must reproduce); stamped on the node clock for offline sync.
        self._norm_pub = self.create_publisher(TwistStamped, "cmd_norm", 10)
        # Arm + LED: latched, published only when a fresh command arrives (the
        # firmware holds them), so they never decay like the drive Twist.
        self._servo_pub = self.create_publisher(Float32MultiArray, "servo_cmd", 10)
        self._led_pub = self.create_publisher(Bool, "led_cmd", 10)

        self._server = _CommandWsServer(
            host, port, self._store, ping_interval, ping_timeout
        )
        self._server.start()

        rate = float(self.get_parameter("publish_rate").value)
        self._timer = self.create_timer(1.0 / rate, self._tick)

        self.get_logger().info(f"teleop_server up: ws://{host}:{port} -> cmd_vel")

    def _tick(self) -> None:
        """Publish the latest command on cmd_vel, plus its normalised twin on
        cmd_norm for logging; both zero if the client is stale / unmanned."""
        vx_norm, wz_norm, age, has_client = self._store.snapshot()
        live = has_client and age <= self._hold_timeout

        twist = Twist()
        norm_vx, norm_wz = 0.0, 0.0
        if live:
            vx, wz = command_to_twist(
                vx_norm, wz_norm, self._max_linear, self._max_angular, self._deadzone
            )
            twist.linear.x = vx
            twist.angular.z = wz
            norm_vx, norm_wz = command_to_norm(vx_norm, wz_norm)
        self._pub.publish(twist)
        self._publish_norm(norm_vx, norm_wz)
        self._publish_latched()

    def _publish_latched(self) -> None:
        """Publish a pending arm / LED command once, if one arrived since the last
        tick. Set-and-hold: no client-liveness gate and no decay -- the firmware
        keeps the last servo pulse / LED state on its own, unlike the wheels."""
        servo = self._store.take_servo()
        if servo is not None:
            self._servo_pub.publish(Float32MultiArray(data=[servo[0], servo[1]]))
        led = self._store.take_led()
        if led is not None:
            self._led_pub.publish(Bool(data=led))

    def _publish_norm(self, vx: float, wz: float) -> None:
        """Publish the normalised command (vx, wz in [-1, 1]) on cmd_norm, stamped
        on the same clock as the camera frames so an offline converter can pair
        each action with the image in effect at that instant."""
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.twist.linear.x = vx
        msg.twist.angular.z = wz
        self._norm_pub.publish(msg)

    def shutdown(self) -> None:
        """Stop the server and send a final explicit zero on both topics."""
        self._server.shutdown()
        self._pub.publish(Twist())
        self._publish_norm(0.0, 0.0)


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
