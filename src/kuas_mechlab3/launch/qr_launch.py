"""Launch the QR-code reader for the ML3 QR task (課題 #5).

Subscribes to the front camera's CompressedImage topic (published by camera_node
/ cameras_launch) -- it does NOT open the /dev/video* device, so it runs
alongside cameras_launch / start-all.sh without contending for the webcam. It
decodes with OpenCV's built-in QRCodeDetector, publishes the payload to
qr_topic, and lights the onboard LED (led_cmd) while a code is readable:

    ros2 launch kuas_mechlab3 qr_launch.py decode_interval:=0.5

``decode_interval`` rate-limits the decode (~70-105 ms/frame on the robot) so the
traffic-light detector (#9) -- which shares this Pi and this camera, and unlike
the QR task must catch the green within a window -- keeps its headroom. The
default 0.5 s (2 Hz) still refreshes the 1 s LED watchdog with margin; at the
previous 0.2 s the decode cost ~25-40% CPU and, alongside YOLO, starved the
camera pipeline (14 Hz with stalls up to 1.9 s measured on the robot -- at
0.5 s it recovered to a steady 24 Hz).

Needs a camera publishing frames (cameras_launch or a camera_node). OpenCV is
already a runtime dependency of the camera path, so this adds no new package.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Bring up the QR reader subscribed to the camera topic."""
    # ParameterValue pins the type so the string launch args reach the typed
    # node parameters as float (a bare substitution would stay a string).
    image_topic = LaunchConfiguration("image_topic")
    off_timeout = ParameterValue(LaunchConfiguration("off_timeout"), value_type=float)
    decode_interval = ParameterValue(
        LaunchConfiguration("decode_interval"), value_type=float
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "image_topic",
                default_value="/front_camera/image_raw/compressed",
            ),
            DeclareLaunchArgument("off_timeout", default_value="1.0"),
            DeclareLaunchArgument("decode_interval", default_value="0.5"),
            Node(
                package="kuas_mechlab3",
                executable="qr_detector",
                name="qr_detector",
                output="screen",
                parameters=[
                    {
                        "image_topic": image_topic,
                        "off_timeout": off_timeout,
                        "decode_interval": decode_interval,
                    }
                ],
            ),
        ]
    )
