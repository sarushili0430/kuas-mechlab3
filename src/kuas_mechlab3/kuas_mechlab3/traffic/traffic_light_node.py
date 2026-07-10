"""ROS2 traffic-light node: camera -> YOLO detect -> team-tagged status.

Owns the camera loop and the OpenCV colour masking; the colour decision and the
on-field message format are delegated to ``light_logic`` (pure, pytest-covered).
When a traffic light is in view its colour is published to
``traffic_light_topic`` as ``<team><Color>`` (e.g. ``"11Green"``) -- the string
the on-field barrier opens for. See the ML3 brief: team 11 sends ``"11Green"``.

Requires ``ultralytics`` (YOLOv8), which is a pip package rather than a rosdep
key, so install it into the ROS2 Python env once: ``pip install ultralytics``.
"""

from typing import Any

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from ultralytics import YOLO

from kuas_mechlab3.traffic.light_logic import classify_color, format_team_message

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
    """Detect a traffic light and publish its team-tagged colour status."""

    def __init__(self) -> None:
        """Declare parameters, load the YOLO model, open the camera."""
        super().__init__("traffic_light_node")

        self.declare_parameter("team_number", 11)
        self.declare_parameter("camera_index", 0)
        self.declare_parameter("model", "yolov8n.pt")
        self.declare_parameter("imgsz", 256)
        self.declare_parameter("show_window", False)

        self._team_number = int(self.get_parameter("team_number").value)
        self._imgsz = int(self.get_parameter("imgsz").value)
        self._show_window = bool(self.get_parameter("show_window").value)
        model_path = str(self.get_parameter("model").value)
        camera_index = int(self.get_parameter("camera_index").value)

        self._pub = self.create_publisher(String, "traffic_light_topic", 10)
        self._model = YOLO(model_path)
        self._cap = cv2.VideoCapture(camera_index)

        self.get_logger().info(
            f"traffic_light up: team={self._team_number} -> {self._pub.topic_name}"
        )

    def run(self) -> None:
        """Grab frames and publish the light status until stopped (q / Ctrl-C)."""
        while rclpy.ok():
            ok, frame = self._cap.read()
            if not ok:
                continue
            self._process_frame(frame)
            if self._show_window and (cv2.waitKey(1) & 0xFF) == ord("q"):
                break

    def _process_frame(self, frame: Any) -> None:
        """Detect a light in one frame and publish its team-tagged colour."""
        results = self._model(
            frame,
            classes=[_TRAFFIC_LIGHT_CLASS],
            imgsz=self._imgsz,
            vid_stride=2,
            verbose=False,
        )
        if any(bool(result.boxes) for result in results):
            color = self._classify(frame)
            if color != "unknown":
                msg = String()
                msg.data = format_team_message(self._team_number, color)
                self._pub.publish(msg)
                self.get_logger().info(f"traffic light: {msg.data}")
        if self._show_window and results:
            cv2.imshow("traffic_light", results[0].plot())

    def _classify(self, frame: Any) -> str:
        """Count red / green / yellow HSV pixels and pick the dominant colour."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        red = cv2.countNonZero(cv2.inRange(hsv, _RED_LOW, _RED_HIGH))
        green = cv2.countNonZero(cv2.inRange(hsv, _GREEN_LOW, _GREEN_HIGH))
        yellow = cv2.countNonZero(cv2.inRange(hsv, _YELLOW_LOW, _YELLOW_HIGH))
        return classify_color(red, green, yellow)

    def shutdown(self) -> None:
        """Release the camera and close any preview window for a clean teardown."""
        self._cap.release()
        if self._show_window:
            cv2.destroyAllWindows()


def main(args: list[str] | None = None) -> None:
    """Spin the detector loop, releasing the camera on any exit path."""
    rclpy.init(args=args)
    node = TrafficLightDetector()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
