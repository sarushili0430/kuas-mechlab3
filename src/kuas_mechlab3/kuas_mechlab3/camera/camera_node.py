"""ROS2 camera node: one USB webcam -> sensor_msgs/CompressedImage (JPEG).

Run once per camera (front and rear) with a different node name and device, so
the topics resolve to /front_camera/image_raw/compressed and
/rear_camera/image_raw/compressed. The cv2 device I/O is delegated to
``CameraCapture``; this node JPEG-encodes each frame at the source so only small
compressed frames cross DDS (cheap on a Raspberry Pi), and owns ROS I/O, the
capture timer, and clean teardown.
"""

from typing import Any

import cv2
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage

from kuas_mechlab3.camera.capture import CameraCapture


class CameraNode(Node):  # type: ignore[misc]
    """Publish JPEG frames from a single USB webcam as CompressedImage."""

    def __init__(self) -> None:
        """Declare parameters, open the camera, start the capture timer."""
        super().__init__("camera")

        self.declare_parameter("device", "0")
        self.declare_parameter("width", 320)
        self.declare_parameter("height", 240)
        self.declare_parameter("fps", 30.0)
        self.declare_parameter("codec", "MJPG")
        self.declare_parameter("frame_id", "camera")
        self.declare_parameter("jpeg_quality", 80)

        self._frame_id = str(self.get_parameter("frame_id").value)
        self._quality = int(self.get_parameter("jpeg_quality").value)
        self._device = str(self.get_parameter("device").value)
        fps = float(self.get_parameter("fps").value)

        self._camera = CameraCapture(
            device=self._device,
            width=int(self.get_parameter("width").value),
            height=int(self.get_parameter("height").value),
            fps=fps,
            codec=str(self.get_parameter("codec").value),
        )
        self._camera.open()

        self._pub = self.create_publisher(
            CompressedImage, "~/image_raw/compressed", qos_profile_sensor_data
        )
        self._timer = self.create_timer(1.0 / fps, self._capture)

        self.get_logger().info(
            f"camera up: device={self._device} -> {self._pub.topic_name}"
        )

    def _capture(self) -> None:
        """Grab one frame, JPEG-encode it, and publish; skip on a bad grab."""
        frame = self._camera.read()
        if frame is None:
            self.get_logger().warn(
                "camera grab failed -> skipping frame", throttle_duration_sec=2.0
            )
            return
        msg = self._to_compressed(frame)
        if msg is not None:
            self._pub.publish(msg)

    def _to_compressed(self, frame: Any) -> CompressedImage | None:
        """JPEG-encode a raw BGR frame into a stamped CompressedImage, or None."""
        ok, buf = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self._quality]
        )
        if not ok:
            self.get_logger().warn(
                "jpeg encode failed -> skipping frame", throttle_duration_sec=2.0
            )
            return None
        msg = CompressedImage()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id
        msg.format = "jpeg"
        msg.data = buf.tobytes()
        return msg

    def shutdown(self) -> None:
        """Release the camera device for a clean teardown."""
        self._camera.close()


def main(args: list[str] | None = None) -> None:
    """Spin the camera node, releasing the device on any exit path."""
    rclpy.init(args=args)
    node = CameraNode()
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
