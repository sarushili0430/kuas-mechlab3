"""Keyboard teleop: translate held keys into cmd_vel Twist messages.

Owns terminal/tty handling only. Publishes geometry_msgs/Twist on cmd_vel at a
steady rate; a held key re-arms a hold timer and releasing it lets the velocity
decay to zero (the driver's watchdog is the real safety net). The serial port
and the kinematics stay entirely out of this node.

The arm shares the keyboard: i/k and o/l jog the shoulder / elbow targets in
degrees (h re-homes both) and each fresh pose is published as a latched
[shoulder_deg, elbow_deg] pair on servo_cmd (std_msgs/Float32MultiArray) -- the
same set-and-hold contract as ``teleop_server``, so unlike the wheels there is
no decay and no watchdog: the firmware holds the last pose on its own, and the
angle->pulse calibration stays downstream in ``protocol.angle_to_us``.
"""

import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray

from kuas_mechlab3.utils import clamp

# Arm jog span / home in degrees: the span ``protocol.angle_to_us`` maps onto
# the [500, 2500] us pulse band, and the same 90/90 home pose the cockpit uses.
ARM_MIN_DEG = 0.0
ARM_MAX_DEG = 180.0
ARM_HOME_DEG = 90.0

# Arm jog keys -> (joint index in [shoulder, elbow], step sign). Signs follow
# the cockpit (docs/cockpit.html): + is each joint's CCW direction.
_ARM_KEYS = {
    "i": (0, 1.0),
    "k": (0, -1.0),
    "o": (1, 1.0),
    "l": (1, -1.0),
}

BANNER = """\
============================================
      ML3 Twist Teleop  (-> cmd_vel)
============================================
   HOLD a key to move -- release to stop:
   w = forward        s = backward
   a = turn left      d = turn right
   q = stop           Ctrl+C = quit (auto-stops)
   TAP/HOLD to jog the arm (it holds its pose):
   i = shoulder +     k = shoulder -
   o = elbow +        l = elbow -
   h = arm home (90/90)
============================================"""


class TeleopKeyboard(Node):  # type: ignore[misc]
    """Read the keyboard: Twist commands on cmd_vel, arm poses on servo_cmd."""

    def __init__(self) -> None:
        """Declare parameters and start the publish/poll timer."""
        super().__init__("teleop_keyboard")
        self.declare_parameter("linear_speed", 0.5)
        self.declare_parameter("angular_speed", 2.0)
        self.declare_parameter("hold_timeout", 0.4)
        self.declare_parameter("publish_rate", 20.0)
        self.declare_parameter("arm_step", 1.5)

        self._lin = float(self.get_parameter("linear_speed").value)
        self._ang = float(self.get_parameter("angular_speed").value)
        self._hold_timeout = float(self.get_parameter("hold_timeout").value)
        self._arm_step = float(self.get_parameter("arm_step").value)

        self._pub = self.create_publisher(Twist, "cmd_vel", 10)
        # Arm: latched set-and-hold target, published only on a fresh key event
        # (the firmware holds the last pulse), so it never decays like the Twist.
        self._servo_pub = self.create_publisher(Float32MultiArray, "servo_cmd", 10)
        self._target = Twist()
        self._arm = [ARM_HOME_DEG, ARM_HOME_DEG]
        self._last_key_t = self.get_clock().now()

        rate = float(self.get_parameter("publish_rate").value)
        self._timer = self.create_timer(1.0 / rate, self._tick)

    def publish_stop(self) -> None:
        """Publish a single zero Twist (explicit stop; the arm keeps its pose)."""
        self._pub.publish(Twist())

    def _set(self, lin: float, ang: float) -> None:
        """Set the current target velocity and re-arm the hold timer."""
        self._target.linear.x = lin
        self._target.angular.z = ang
        self._last_key_t = self.get_clock().now()

    def _jog_arm(self, key: str) -> None:
        """Apply one arm key event: jog a joint by arm_step, or re-home on h."""
        if key == "h":
            self._arm = [ARM_HOME_DEG, ARM_HOME_DEG]
            return
        joint, sign = _ARM_KEYS[key]
        self._arm[joint] = clamp(
            self._arm[joint] + sign * self._arm_step, ARM_MIN_DEG, ARM_MAX_DEG
        )

    def _tick(self) -> None:
        """Process buffered keystrokes, apply hold-timeout decay, publish."""
        arm_fresh = False
        for key in _read_keys():
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
            elif key == "h" or key in _ARM_KEYS:
                self._jog_arm(key)
                arm_fresh = True

        age = (self.get_clock().now() - self._last_key_t).nanoseconds * 1e-9
        if age > self._hold_timeout:
            self._target.linear.x = 0.0
            self._target.angular.z = 0.0

        self._pub.publish(self._target)
        # Latched, like teleop_server: forward each fresh arm pose once -- held
        # keys repeat via tty auto-repeat, so the jog rate follows the keyboard.
        if arm_fresh:
            self._servo_pub.publish(
                Float32MultiArray(data=[self._arm[0], self._arm[1]])
            )


def _read_keys() -> str:
    """Return every buffered keystroke without blocking ('' if none).

    Draining the whole buffer each tick keeps key auto-repeat (usually faster
    than the tick rate) from backlogging in the tty and replaying after release;
    the empty-read guard stops the loop at EOF, where select() stays readable.
    """
    keys = ""
    while select.select([sys.stdin], [], [], 0)[0]:
        char = sys.stdin.read(1)
        if not char:
            break
        keys += char
    return keys


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
