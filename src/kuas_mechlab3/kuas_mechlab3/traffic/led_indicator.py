"""ROS2 node: mirror green traffic-light detection onto the onboard LED.

Subscribes ``traffic_light_topic`` (the team-tagged ``<team><Color>`` status the
detector publishes) and drives ``led_cmd`` (Bool -- the same topic the cockpit's
manual LED button and ``mbed_driver`` use) so the onboard LED is lit only while
the team's green light is in view. The on/off decision -- a green-token match
plus a watchdog that clears the LED shortly after the light leaves the frame and
the status topic goes silent -- lives in the pure ``led_logic.LedPolicy`` so it
is unit-tested without ROS. Edge-triggered: a command is published only when the
LED state changes, so it neither spams ``led_cmd`` nor needlessly fights manual
LED control except at a green transition.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, String

from kuas_mechlab3.traffic.led_logic import LedPolicy


class LedIndicator(Node):  # type: ignore[misc]
    """Light the onboard LED while the team's green light is detected."""

    def __init__(self) -> None:
        """Declare parameters and wire the status sub, LED pub, and watchdog timer."""
        super().__init__("led_indicator")

        self.declare_parameter("team_number", 11)
        self.declare_parameter("off_timeout", 1.0)
        self.declare_parameter("status_topic", "traffic_light_topic")
        self.declare_parameter("led_topic", "led_cmd")

        team_number = int(self.get_parameter("team_number").value)
        off_timeout = float(self.get_parameter("off_timeout").value)
        status_topic = str(self.get_parameter("status_topic").value)
        led_topic = str(self.get_parameter("led_topic").value)

        self._policy = LedPolicy(
            green_token=f"{team_number}Green", off_timeout_s=off_timeout
        )
        self._pub = self.create_publisher(Bool, led_topic, 10)
        self._sub = self.create_subscription(String, status_topic, self._on_status, 10)
        # Watchdog: without it the LED would latch on after the light leaves view
        # (the status topic simply goes silent). 5 Hz clears it within off_timeout.
        self._timer = self.create_timer(0.2, self._on_tick)

        self.get_logger().info(
            f"led_indicator up: {status_topic} == {team_number}Green "
            f"-> {led_topic} (off {off_timeout}s after light leaves view)"
        )

    def _now_s(self) -> float:
        """The node clock in seconds -- the time unit the policy expects."""
        return float(self.get_clock().now().nanoseconds) / 1e9

    def _on_status(self, msg: String) -> None:
        """Feed a detector status string to the policy and apply any LED change."""
        self._apply(self._policy.on_message(msg.data, self._now_s()))

    def _on_tick(self) -> None:
        """Run the watchdog and apply any LED change (light removed -> off)."""
        self._apply(self._policy.on_tick(self._now_s()))

    def _apply(self, new_state: bool | None) -> None:
        """Publish ``led_cmd`` only when the policy reports a state change."""
        if new_state is not None:
            self._pub.publish(Bool(data=new_state))
            self.get_logger().info(f"LED -> {'ON' if new_state else 'OFF'}")


def main(args: list[str] | None = None) -> None:
    """Spin the LED indicator until interrupted."""
    rclpy.init(args=args)
    node = LedIndicator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
