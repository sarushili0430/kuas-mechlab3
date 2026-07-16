"""ROS node: read QR codes from the front camera and light the onboard LED.

Subscribes the front camera's CompressedImage topic (it does NOT open
/dev/video*, so it runs alongside cameras_launch without contending for the
webcam), decodes with OpenCV's built-in ``QRCodeDetector``, publishes the
payload to ``qr_topic`` and drives the onboard LED (``led_cmd``) while a code is
readable.

The lit/clear decision lives in the pure ``qr_logic.QrLedPolicy`` (pytest); this
node is the thin wiring: decode -> policy -> publish.

    ros2 run kuas_mechlab3 qr_detector --ros-args -p off_timeout:=1.0

OpenCV's detector needs no extra dependency (cv2 is already required by the
camera path); it decoded ~76% of live 320x240 frames on the robot, including
while the card was rotated, so pyzbar/libzbar is deliberately not used.
"""

import cv2
import numpy as np
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Bool, String

from kuas_mechlab3.traffic.qr_logic import QrLedPolicy
from kuas_mechlab3.traffic.throttle import DecodeThrottle


class QrDetector(Node):  # type: ignore[misc]
    """Decode QR codes from the front camera and drive the onboard LED."""

    def __init__(self) -> None:
        super().__init__("qr_detector")
        self.declare_parameter("off_timeout", 1.0)
        self.declare_parameter("decode_interval", 0.2)
        self.declare_parameter("image_topic", "/front_camera/image_raw/compressed")
        self.declare_parameter("qr_topic", "qr_topic")
        self.declare_parameter("led_topic", "led_cmd")

        off_timeout = float(self.get_parameter("off_timeout").value)
        decode_interval = float(self.get_parameter("decode_interval").value)
        image_topic = str(self.get_parameter("image_topic").value)
        qr_topic = str(self.get_parameter("qr_topic").value)
        led_topic = str(self.get_parameter("led_topic").value)

        # The Pi has no RTC: its wall clock is restored to a stale value at boot
        # and jumps (~24h observed) when NTP corrects it. A backwards jump would
        # make the watchdog's elapsed time negative and defeat it, so the policy
        # is driven from a monotonic clock rather than get_clock() (SYSTEM_TIME).
        self._clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._detector = cv2.QRCodeDetector()
        self._policy = QrLedPolicy(off_timeout_s=off_timeout)
        self._throttle = DecodeThrottle(interval_s=decode_interval)

        self._qr_pub = self.create_publisher(String, qr_topic, 10)
        self._led_pub = self.create_publisher(Bool, led_topic, 10)
        # Match camera_node's sensor QoS (best-effort) or no frames arrive.
        self._sub = self.create_subscription(
            CompressedImage, image_topic, self._on_image, qos_profile_sensor_data
        )
        # Frames alone drive the watchdog while the camera is publishing; this
        # timer covers the camera going silent entirely (a dead camera must not
        # leave the LED stuck on).
        self._timer = self.create_timer(0.2, self._on_tick)

        self.get_logger().info(
            f"qr_detector up: {image_topic} -> {self._qr_pub.topic_name} "
            f"+ {self._led_pub.topic_name} (off_timeout={off_timeout}s)"
        )

    def _now_s(self) -> float:
        return float(self._clock.now().nanoseconds) / 1e9

    def _on_image(self, msg: CompressedImage) -> None:
        """Decode one frame (rate-limited), publish the payload, apply the policy."""
        now = self._now_s()
        # Bail before the JPEG decode so a skipped frame costs nothing: this node
        # shares the Pi and the camera with the traffic-light detector (#9), which
        # unlike the QR task has a timing requirement. The watchdog runs off the
        # timer, so skipping frames cannot strand the LED on.
        if not self._throttle.should_decode(now):
            return
        frame = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return
        try:
            payload, _points, _ = self._detector.detectAndDecode(frame)
        except cv2.error:
            # A malformed frame must not kill the node mid-run.
            return
        if payload:
            self._qr_pub.publish(String(data=payload))
        self._apply(self._policy.on_qr(payload, now))

    def _on_tick(self) -> None:
        self._apply(self._policy.on_tick(self._now_s()))

    def _apply(self, state: bool | None) -> None:
        """Publish ``led_cmd`` only when the policy reports a state change."""
        if state is None:
            return
        self._led_pub.publish(Bool(data=state))
        self.get_logger().info(f"LED -> {'ON' if state else 'OFF'}")


def main() -> None:
    rclpy.init()
    node = QrDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
