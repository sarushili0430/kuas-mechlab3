"""Keyboard teleop: translate keys into cmd_vel Twist and servo_cmd arm moves.

Owns terminal/tty handling only. Two independent output paths:

  * DRIVE -- WASD publishes geometry_msgs/Twist on cmd_vel at a steady rate; a
    held key re-arms a hold timer and releasing it lets the velocity decay to
    zero (the driver's watchdog is the real safety net).
  * ARM   -- the arrow keys nudge a held shoulder/elbow target and publish
    std_msgs/Float32MultiArray [shoulder_deg, elbow_deg] on servo_cmd. The
    firmware latches servo pulses (no watchdog), so the target is published
    only when an arrow key changes it -- never every tick like cmd_vel.

The serial port and the kinematics stay entirely out of this node; it only
speaks the ROS topics mbed_driver already subscribes to (cmd_vel / servo_cmd).
"""

import os
import select
import sys
import termios
import tty

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from std_msgs.msg import Float32MultiArray

ARM_MIN_DEG = 0.0
ARM_MAX_DEG = 180.0

BANNER = """\
============================================
   ML3 Twist + Arm Teleop (cmd_vel/servo_cmd)
============================================
   DRIVE -- hold a key, release to stop:
     w = forward        s = backward
     a = turn left      d = turn right
     q = stop
   ARM -- arrow keys nudge & hold:
     Up / Down    = elbow    + / -   (vertical)
     Right / Left = shoulder + / -   (horizontal)
   Ctrl+C = quit (auto-stops the wheels)
============================================"""


class TeleopKeyboard(Node):  # type: ignore[misc]
    """Read the keyboard and publish cmd_vel (drive) and servo_cmd (arm)."""

    def __init__(self) -> None:
        """Declare parameters and start the publish/poll timer."""
        super().__init__("teleop_keyboard")
        self.declare_parameter("linear_speed", 0.5)
        self.declare_parameter("angular_speed", 2.0)
        self.declare_parameter("hold_timeout", 0.4)
        self.declare_parameter("publish_rate", 20.0)
        self.declare_parameter("arm_step", 2.0)
        self.declare_parameter("shoulder_start_deg", 90.0)
        self.declare_parameter("elbow_start_deg", 90.0)

        self._lin = float(self.get_parameter("linear_speed").value)
        self._ang = float(self.get_parameter("angular_speed").value)
        self._hold_timeout = float(self.get_parameter("hold_timeout").value)
        self._arm_step = float(self.get_parameter("arm_step").value)

        # Arm target starts at the assumed neutral pose but is NOT published on
        # startup: the servos are open-loop set-and-hold, so we leave the arm
        # wherever it physically is until the first arrow key commands a move.
        self._shoulder = _clamp_deg(
            float(self.get_parameter("shoulder_start_deg").value)
        )
        self._elbow = _clamp_deg(float(self.get_parameter("elbow_start_deg").value))

        self._pub = self.create_publisher(Twist, "cmd_vel", 10)
        self._servo_pub = self.create_publisher(Float32MultiArray, "servo_cmd", 10)
        self._target = Twist()
        self._last_key_t = self.get_clock().now()

        rate = float(self.get_parameter("publish_rate").value)
        self._timer = self.create_timer(1.0 / rate, self._tick)

    def publish_stop(self) -> None:
        """Publish a single zero Twist (explicit stop). Arm is left holding."""
        self._pub.publish(Twist())

    def _set(self, lin: float, ang: float) -> None:
        """Set the current drive target velocity and re-arm the hold timer."""
        self._target.linear.x = lin
        self._target.angular.z = ang
        self._last_key_t = self.get_clock().now()

    def _nudge_arm(self, d_shoulder: float, d_elbow: float) -> None:
        """Adjust the held arm target by a step and publish it once.

        Only called on an arrow keystroke, so servo_cmd is published on change
        rather than every tick -- matching the firmware's set-and-hold servos.
        """
        self._shoulder = _clamp_deg(self._shoulder + d_shoulder)
        self._elbow = _clamp_deg(self._elbow + d_elbow)
        self._servo_pub.publish(Float32MultiArray(data=[self._shoulder, self._elbow]))
        print(
            f"\rarm: shoulder={self._shoulder:5.1f}  elbow={self._elbow:5.1f}   ",
            end="",
            flush=True,
        )

    def _apply_key(self, key: str) -> None:
        """Route one decoded keystroke to the drive or the arm path."""
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
        # Up/Down drive the vertical joint (elbow); Left/Right the horizontal
        # joint (shoulder) -- matching how the arm actually moves on the robot.
        elif key == "UP":
            self._nudge_arm(0.0, self._arm_step)
        elif key == "DOWN":
            self._nudge_arm(0.0, -self._arm_step)
        elif key == "RIGHT":
            self._nudge_arm(self._arm_step, 0.0)
        elif key == "LEFT":
            self._nudge_arm(-self._arm_step, 0.0)

    def _tick(self) -> None:
        """Drain buffered keys, apply hold-timeout decay, publish the drive target."""
        while True:
            key = _read_key()
            if not key:
                break
            self._apply_key(key)

        age = (self.get_clock().now() - self._last_key_t).nanoseconds * 1e-9
        if age > self._hold_timeout:
            self._target.linear.x = 0.0
            self._target.angular.z = 0.0

        self._pub.publish(self._target)


def _clamp_deg(deg: float) -> float:
    """Saturate an arm angle to the [ARM_MIN_DEG, ARM_MAX_DEG] range."""
    return max(ARM_MIN_DEG, min(ARM_MAX_DEG, deg))


_ARROW_NAMES = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}


def _read_byte() -> str:
    """Read exactly one pending byte from stdin, at the fd level, or '' if none.

    Uses os.read on the raw file descriptor rather than sys.stdin.read: a
    buffered sys.stdin would pull a whole escape sequence into its own user-space
    buffer on the first read, after which select() -- which only sees the fd --
    reports "no input" and the buffered '[A' suffix is dropped (arrow keys then
    never decode). Keeping both select() and the read on the same fd, one byte at
    a time, means a read never over-reads and the next select() stays truthful.
    """
    if not select.select([sys.stdin], [], [], 0)[0]:
        return ""
    data = os.read(sys.stdin.fileno(), 1)
    return data.decode("latin-1") if data else ""


def _read_key() -> str:
    """Return one keystroke token without blocking, or '' if none is ready.

    Ordinary keys come back as themselves (e.g. 'w'). The four arrow keys, which
    the terminal sends as a 3-byte CSI escape (ESC '[' 'A'..'D'), are decoded to
    'UP' / 'DOWN' / 'RIGHT' / 'LEFT' so callers match on a name, not raw bytes.
    A lone ESC (no CSI follow-up ready) returns '' and is ignored.
    """
    ch = _read_byte()
    if ch != "\x1b":
        return ch
    if _read_byte() != "[":
        return ""
    return _ARROW_NAMES.get(_read_byte(), "")


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
        print()  # leave the cursor on a fresh line after the arm status
        node.publish_stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
