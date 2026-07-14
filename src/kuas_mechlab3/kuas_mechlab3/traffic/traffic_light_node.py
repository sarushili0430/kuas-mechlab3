"""ROS2 traffic-light node: camera topic in -> YOLO detect -> team-tagged status.

Consumes the shared camera stream the same way ``mjpeg_server`` does: it
subscribes to a ``sensor_msgs/CompressedImage`` topic (the front camera by
default) instead of opening the ``/dev/video*`` device itself, so it never
contends with ``camera_node`` for the webcam and composes cleanly with
``cameras_launch`` / ``start-all.sh``. When a traffic light is in view its
colour is published to ``traffic_light_topic`` as ``<team><Color>`` (e.g.
``"11Green"``) -- the string the on-field barrier opens for. See the ML3 brief:
team 11 sends ``"11Green"``.

The input decode (JPEG bytes -> BGR frame) and the YOLO / HSV detection live
here; the publish decision (detection + colour -> the exact wire string, or
nothing) is delegated to ``light_logic.status_message`` so that output IO
contract is unit-tested by pytest without a ROS2 environment or a camera.

Requires ``ultralytics`` (YOLOv8), a pip package rather than a rosdep key:
``pip install ultralytics``.
"""

from typing import Any

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from ultralytics import YOLO

from kuas_mechlab3.traffic.light_logic import status_message

# COCO class id 9 is "traffic light" -- restrict YOLO to just that class.
_TRAFFIC_LIGHT_CLASS = 9

# HSV inRange bounds (OpenCV hue is 0..179) for each light colour.
_RED_LOW = np.array([0, 120, 70])
_RED_HIGH = np.array([10, 255, 255])
_GREEN_LOW = np.array([45, 100, 50])
_GREEN_HIGH = np.array([75, 255, 255])
_YELLOW_LOW = np.array([20, 100, 100])
_YELLOW_HIGH = np.array([30, 255, 255])


class TrafficLightDetector(Node):  # type: ignore[misc]
    """Subscribe to a camera topic and publish the team-tagged light status."""

    def __init__(self) -> None:
        """Declare parameters, load YOLO, wire up the camera sub and status pub."""
        super().__init__("traffic_light_node")

        self.declare_parameter("team_number", 11)
        self.declare_parameter("image_topic", "/front_camera/image_raw/compressed")
        self.declare_parameter("model", "yolov8n.pt")
        self.declare_parameter("imgsz", 256)
        self.declare_parameter("show_window", False)

        self._team_number = int(self.get_parameter("team_number").value)
        self._imgsz = int(self.get_parameter("imgsz").value)
        self._show_window = bool(self.get_parameter("show_window").value)
        model_path = str(self.get_parameter("model").value)
        image_topic = str(self.get_parameter("image_topic").value)

        self._model = YOLO(model_path)
        self._pub = self.create_publisher(String, "traffic_light_topic", 10)
        # Match camera_node's sensor QoS (best-effort) or no frames arrive.
        self._sub = self.create_subscription(
            CompressedImage, image_topic, self._on_image, qos_profile_sensor_data
        )

        self.get_logger().info(
            f"traffic_light up: team={self._team_number} "
            f"{image_topic} -> {self._pub.topic_name}"
        )

    def _on_image(self, msg: CompressedImage) -> None:
        """Decode one camera frame and publish its team-tagged colour status."""
        frame = cv2.imdecode(
            np.frombuffer(bytes(msg.data), dtype=np.uint8), cv2.IMREAD_COLOR
        )
        if frame is None:
            self.get_logger().warn(
                "could not decode camera frame -> skipping", throttle_duration_sec=2.0
            )
            return
        detected, red, green, yellow = self._detect(frame)
        data = status_message(detected, red, green, yellow, self._team_number)
        if data is not None:
            self._pub.publish(String(data=data))
            self.get_logger().info(f"traffic light: {data}")
        if self._show_window:
            cv2.imshow("traffic_light", frame)
            cv2.waitKey(1)

    def _detect(self, frame: Any) -> tuple[bool, int, int, int]:
        """Return (light in view?, red, green, yellow HSV pixel counts) for a frame."""
        results = self._model(
            frame,
            classes=[_TRAFFIC_LIGHT_CLASS],
            imgsz=self._imgsz,
            vid_stride=2,
            verbose=False,
        )
        detected = any(bool(result.boxes) for result in results)
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        red = cv2.countNonZero(cv2.inRange(hsv, _RED_LOW, _RED_HIGH))
        green = cv2.countNonZero(cv2.inRange(hsv, _GREEN_LOW, _GREEN_HIGH))
        yellow = cv2.countNonZero(cv2.inRange(hsv, _YELLOW_LOW, _YELLOW_HIGH))
        return detected, int(red), int(green), int(yellow)

    def shutdown(self) -> None:
        """Close any preview window for a clean teardown."""
        if self._show_window:
            cv2.destroyAllWindows()


def main(args: list[str] | None = None) -> None:
    """Spin the detector until interrupted."""
    rclpy.init(args=args)
    node = TrafficLightDetector()
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
