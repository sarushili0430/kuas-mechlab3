"""ROS2 driver node: Twist in, mbed serial out, telemetry published back.

Responsibilities owned here:
  * ROS I/O   -- subscribe cmd_vel (geometry_msgs/Twist); publish wheel rpm/pwm
  * arm I/O   -- subscribe servo_cmd (std_msgs/Float32MultiArray, joint angles)
  * failsafe  -- watchdog stop when cmd_vel goes stale; final stop on shutdown

Mixing is delegated to ``kinematics`` and the wire format to ``protocol`` /
``SerialLink``, so this node never touches raw bytes or robot geometry directly.

Servos share the one serial port this node owns, so servo commands are forwarded
from here too (over the separate 'a'-terminated packet). They are open-loop and
hold their last position, so -- unlike cmd_vel -- there is no servo watchdog: a
stale servo_cmd simply leaves the arm where it is.
"""

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray

from kuas_mechlab3.drive.kinematics import twist_to_setpoints
from kuas_mechlab3.drive.protocol import Telemetry, angle_to_us, parse_telemetry
from kuas_mechlab3.drive.serial_link import SerialLink


class MbedDriver(Node):  # type: ignore[misc]
    """Bridge between the ROS cmd_vel topic and the mbed motor firmware."""

    def __init__(self) -> None:
        """Declare parameters, open the serial link, wire up pub/sub/timers."""
        super().__init__("mbed_driver")

        self.declare_parameter("port", "/dev/ttyACM0")
        self.declare_parameter("baud", 115200)
        self.declare_parameter("max_linear", 0.5)
        self.declare_parameter("max_angular", 2.0)
        self.declare_parameter("wheel_setpoint", 10.5)
        self.declare_parameter("turn_sign", 1.0)
        self.declare_parameter("cmd_timeout", 0.4)
        self.declare_parameter("telemetry_rate", 50.0)
        self.declare_parameter("servo_min_us", 500)
        self.declare_parameter("servo_max_us", 2500)
        self.declare_parameter("servo_min_deg", 0.0)
        self.declare_parameter("servo_max_deg", 180.0)

        self._max_linear = float(self.get_parameter("max_linear").value)
        self._max_angular = float(self.get_parameter("max_angular").value)
        self._wheel_setpoint = float(self.get_parameter("wheel_setpoint").value)
        self._turn_sign = float(self.get_parameter("turn_sign").value)
        self._cmd_timeout = float(self.get_parameter("cmd_timeout").value)
        self._servo_min_us = int(self.get_parameter("servo_min_us").value)
        self._servo_max_us = int(self.get_parameter("servo_max_us").value)
        self._servo_min_deg = float(self.get_parameter("servo_min_deg").value)
        self._servo_max_deg = float(self.get_parameter("servo_max_deg").value)
        port = str(self.get_parameter("port").value)
        baud = int(self.get_parameter("baud").value)

        self._link = SerialLink(port, baud)
        self._link.open()

        self._last_cmd_t = self.get_clock().now()
        self._stopped = True
        self._send_stop()  # known-safe state on launch

        self._sub = self.create_subscription(Twist, "cmd_vel", self._on_cmd_vel, 10)
        self._servo_sub = self.create_subscription(
            Float32MultiArray, "servo_cmd", self._on_servo_cmd, 10
        )
        self._rpm_pub = self.create_publisher(Float32MultiArray, "~/wheel_rpm", 10)
        self._pwm_pub = self.create_publisher(Float32MultiArray, "~/wheel_pwm", 10)

        rate = float(self.get_parameter("telemetry_rate").value)
        self._telemetry_timer = self.create_timer(1.0 / rate, self._poll_serial)
        self._watchdog_timer = self.create_timer(0.05, self._check_watchdog)

        self.get_logger().info(f"mbed_driver up: cmd_vel -> {port}")

    def _on_cmd_vel(self, msg: Twist) -> None:
        """Mix an incoming Twist to setpoints and forward them to the firmware."""
        setpoints = twist_to_setpoints(
            msg.linear.x,
            msg.angular.z,
            self._max_linear,
            self._max_angular,
            self._wheel_setpoint,
            self._turn_sign,
        )
        self._link.send_setpoints(*setpoints)
        self._last_cmd_t = self.get_clock().now()
        self._stopped = all(v == 0.0 for v in setpoints)

    def _on_servo_cmd(self, msg: Float32MultiArray) -> None:
        """Map two joint angles (deg) to servo pulses and forward to the firmware.

        Expects ``data = [shoulder_deg, elbow_deg]``; extra entries are ignored,
        fewer than two is dropped with a warning. Open-loop and no watchdog: the
        arm holds the last commanded pose until the next servo_cmd (or reset).
        """
        angles = list(msg.data)
        if len(angles) < 2:
            self.get_logger().warn(
                f"servo_cmd needs 2 angles, got {len(angles)} -- ignored"
            )
            return
        us = [
            angle_to_us(
                float(angles[i]),
                self._servo_min_deg,
                self._servo_max_deg,
                self._servo_min_us,
                self._servo_max_us,
            )
            for i in range(2)
        ]
        self._link.send_servo_us(us[0], us[1])

    def _check_watchdog(self) -> None:
        """Stop the wheels if no fresh cmd_vel arrived within cmd_timeout."""
        if self._stopped:
            return
        age = (self.get_clock().now() - self._last_cmd_t).nanoseconds * 1e-9
        if age > self._cmd_timeout:
            self.get_logger().warn(f"cmd_vel stale ({age:.2f}s) -> stop")
            self._send_stop()

    def _poll_serial(self) -> None:
        """Drain pending telemetry lines and publish the latest rpm / pwm."""
        latest: Telemetry | None = None
        for line in self._link.read_pending():
            parsed = parse_telemetry(line)
            if parsed is not None:
                latest = parsed
        if latest is not None:
            self._rpm_pub.publish(Float32MultiArray(data=latest["rpm"]))
            pwm = [float(v) for v in latest["pwm"]]
            self._pwm_pub.publish(Float32MultiArray(data=pwm))

    def _send_stop(self) -> None:
        """Command all four wheels to zero and mark the driver stopped."""
        self._link.send_setpoints(0.0, 0.0, 0.0, 0.0)
        self._stopped = True

    def shutdown(self) -> None:
        """Best-effort final stop and port release for a clean teardown."""
        try:
            self._send_stop()
        except OSError:
            pass
        self._link.close()


def main(args: list[str] | None = None) -> None:
    """Spin the driver, guaranteeing a final stop on any exit path."""
    rclpy.init(args=args)
    node = MbedDriver()
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
