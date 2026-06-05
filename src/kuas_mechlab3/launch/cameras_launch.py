"""Launch the front + rear webcams and the MJPEG/HTTP teleop viewer.

Brings up two camera nodes (publishing /front_camera/image_raw and
/rear_camera/image_raw) plus mjpeg_server, which streams both to a browser at
http://<pi>:8080/ for a remote teleop operator. Override the device paths per
robot -- prefer the stable /dev/v4l/by-id/... symlinks so front/rear do not swap
across reboots:

    ros2 launch kuas_mechlab3 cameras_launch.py \\
        front_device:=/dev/video0 rear_device:=/dev/video2
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Bring up both webcams and the HTTP streamer."""
    front_device = LaunchConfiguration("front_device")
    rear_device = LaunchConfiguration("rear_device")

    return LaunchDescription(
        [
            DeclareLaunchArgument("front_device", default_value="/dev/video0"),
            DeclareLaunchArgument("rear_device", default_value="/dev/video2"),
            Node(
                package="kuas_mechlab3",
                executable="camera_node",
                name="front_camera",
                output="screen",
                parameters=[
                    {
                        "device": front_device,
                        "frame_id": "front_camera",
                        "width": 640,
                        "height": 480,
                        "fps": 30.0,
                    }
                ],
            ),
            Node(
                package="kuas_mechlab3",
                executable="camera_node",
                name="rear_camera",
                output="screen",
                parameters=[
                    {
                        "device": rear_device,
                        "frame_id": "rear_camera",
                        "width": 640,
                        "height": 480,
                        "fps": 30.0,
                    }
                ],
            ),
            Node(
                package="kuas_mechlab3",
                executable="mjpeg_server",
                name="mjpeg_server",
                output="screen",
                parameters=[
                    {
                        "topics": [
                            "/front_camera/image_raw",
                            "/rear_camera/image_raw",
                        ],
                        "port": 8080,
                    }
                ],
            ),
        ]
    )
