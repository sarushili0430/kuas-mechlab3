"""Keyboard teleop: translate held keys into cmd_vel Twist messages.

Owns terminal/tty handling only. Publishes geometry_msgs/Twist on cmd_vel at a
steady rate; a held key re-arms a hold timer and releasing it lets the velocity
decay to zero (the driver's watchdog is the real safety net). The serial port
and the kinematics stay entirely out of this node.
"""

import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node

BANNER = """\
============================================
      ML3 Twist Teleop  (-> cmd_vel)
============================================
   HOLD a key to move -- release to stop:
   w = forward        s = backward
   a = turn left      d = turn right
   q = stop           Ctrl+C = quit (auto-stops)
============================================"""


class TeleopKeyboard(Node):  # type: ignore[misc]
    """Read the keyboard and publish Twist commands on cmd_vel."""

    def __init__(self) -> None:
        """Declare parameters and start the publish/poll timer."""
        super().__init__("teleop_keyboard")
        self.declare_parameter("linear_speed", 0.5)
        self.declare_parameter("angular_speed", 2.0)
        self.declare_parameter("hold_timeout", 0.4)
        self.declare_parameter("publish_rate", 20.0)

        self._lin = float(self.get_parameter("linear_speed").value)
        self._ang = float(self.get_parameter("angular_speed").value)
        self._hold_timeout = float(self.get_parameter("hold_timeout").value)

        self._pub = self.create_publisher(Twist, "cmd_vel", 10)
        self._target = Twist()
        self._last_key_t = self.get_clock().now()

        rate = float(self.get_parameter("publish_rate").value)
        self._timer = self.create_timer(1.0 / rate, self._tick)

    def publish_stop(self) -> None:
        """Publish a single zero Twist (explicit stop)."""
        self._pub.publish(Twist())

    def _set(self, lin: float, ang: float) -> None:
        """Set the current target velocity and re-arm the hold timer."""
        self._target.linear.x = lin
        self._target.angular.z = ang
        self._last_key_t = self.get_clock().now()

    def _tick(self) -> None:
        """Poll one keystroke, apply hold-timeout decay, publish the target."""
        key = _read_key()
        if key == "w":
            self._set(self._lin, 0.0)
        elif key == "s":
            self._set(-self._lin, 0.0)
        elif key == "a":
            self._set(0.0, self._ang)
        elif key == "d":
            self._set(0.0, -self._ang)
        elif key == "q":
            self._set(0.0, 0.0)

        age = (self.get_clock().now() - self._last_key_t).nanoseconds * 1e-9
        if age > self._hold_timeout:
            self._target.linear.x = 0.0
            self._target.angular.z = 0.0

        self._pub.publish(self._target)


def _read_key() -> str:
    """Return one buffered keystroke without blocking, or '' if none."""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return ""


def main(args: list[str] | None = None) -> None:
    """Run teleop in cbreak mode, restoring the terminal and stopping on exit."""
    rclpy.init(args=args)
    node = TeleopKeyboard()
    print(BANNER, flush=True)
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setcbreak(sys.stdin.fileno())
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        node.publish_stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
