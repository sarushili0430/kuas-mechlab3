"""ROS2 subscriber that prints the team-tagged traffic-light status.

Mirrors the ML3 brief's check step: subscribe to ``traffic_light_topic`` and log
each ``<team><Color>`` message (e.g. ``"11Green"``) the detector publishes, so
you can confirm the team number and colour are going out correctly.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TrafficLightSubscriber(Node):  # type: ignore[misc]
    """Log every team-tagged status published on ``traffic_light_topic``."""

    def __init__(self) -> None:
        """Subscribe to the traffic-light status topic."""
        super().__init__("traffic_light_subscriber")
        self._sub = self.create_subscription(
            String, "traffic_light_topic", self._on_status, 10
        )

    def _on_status(self, msg: String) -> None:
        """Print the received ``<team><Color>`` status string."""
        self.get_logger().info(msg.data)


def main(args: list[str] | None = None) -> None:
    """Spin the subscriber until interrupted."""
    rclpy.init(args=args)
    node = TrafficLightSubscriber()
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
