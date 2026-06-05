"""ROS2 camera node: one USB webcam -> sensor_msgs/Image on ~/image_raw.

Run once per camera (front and rear) with a different node name and device, so
the topics resolve to /front_camera/image_raw and /rear_camera/image_raw. The
cv2 device I/O is delegated to ``CameraCapture`` and the per-message field math
to ``frame``, so this node owns only ROS I/O, the capture timer, and teardown.
"""

from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

from kuas_mechlab3.camera.capture import CameraCapture
from kuas_mechlab3.camera.frame import image_fields


class CameraNode(Node):  # type: ignore[misc]
    """Publish frames from a single USB webcam as sensor_msgs/Image."""

    def __init__(self) -> None:
        """Declare parameters, open the camera, start the capture timer."""
        super().__init__("camera")

        self.declare_parameter("device", "0")
        self.declare_parameter("width", 640)
        self.declare_parameter("height", 480)
        self.declare_parameter("fps", 30.0)
        self.declare_parameter("codec", "MJPG")
        self.declare_parameter("frame_id", "camera")
        self.declare_parameter("encoding", "bgr8")

        self._frame_id = str(self.get_parameter("frame_id").value)
        self._encoding = str(self.get_parameter("encoding").value)
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

        self._pub = self.create_publisher(Image, "~/image_raw", qos_profile_sensor_data)
        self._timer = self.create_timer(1.0 / fps, self._capture)

        self.get_logger().info(
            f"camera up: device={self._device} -> {self._pub.topic_name}"
        )

    def _capture(self) -> None:
        """Grab one frame and publish it; skip (throttled warn) on a bad grab."""
        frame = self._camera.read()
        if frame is None:
            self.get_logger().warn(
                "camera grab failed -> skipping frame", throttle_duration_sec=2.0
            )
            return
        self._pub.publish(self._to_image(frame))

    def _to_image(self, frame: Any) -> Image:
        """Wrap a raw BGR frame in a stamped sensor_msgs/Image message."""
        fields = image_fields(int(frame.shape[0]), int(frame.shape[1]), self._encoding)
        msg = Image()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id
        msg.height = fields["height"]
        msg.width = fields["width"]
        msg.encoding = fields["encoding"]
        msg.is_bigendian = fields["is_bigendian"]
        msg.step = fields["step"]
        msg.data = frame.tobytes()
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
