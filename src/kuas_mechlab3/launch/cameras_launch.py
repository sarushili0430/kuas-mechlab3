"""Launch the front + rear webcams and the MJPEG/HTTP teleop viewer.

Brings up two camera nodes (publishing /front_camera/image_raw/compressed and
/rear_camera/image_raw/compressed as JPEG CompressedImage) plus mjpeg_server,
which relays both to a browser at http://<pi>:8080/ for a remote teleop
operator. Defaults are tuned for a Raspberry Pi (320x240 @30fps); override per
robot, and prefer the stable /dev/v4l/by-id/... symlinks so front/rear do not
swap across reboots:

    ros2 launch kuas_mechlab3 cameras_launch.py \\
        front_device:=/dev/video0 rear_device:=/dev/video2 \\
        width:=640 height:=480 fps:=15.0 stream_fps:=15.0
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Bring up both webcams and the HTTP streamer."""
    front_device = LaunchConfiguration("front_device")
    rear_device = LaunchConfiguration("rear_device")
    # ParameterValue pins the type so the string launch args reach the typed
    # node parameters as int/float (a bare substitution would stay a string).
    width = ParameterValue(LaunchConfiguration("width"), value_type=int)
    height = ParameterValue(LaunchConfiguration("height"), value_type=int)
    fps = ParameterValue(LaunchConfiguration("fps"), value_type=float)
    stream_fps = ParameterValue(LaunchConfiguration("stream_fps"), value_type=float)

    return LaunchDescription(
        [
            DeclareLaunchArgument("front_device", default_value="/dev/video0"),
            DeclareLaunchArgument("rear_device", default_value="/dev/video2"),
            DeclareLaunchArgument("width", default_value="320"),
            DeclareLaunchArgument("height", default_value="240"),
            DeclareLaunchArgument("fps", default_value="30.0"),
            DeclareLaunchArgument("stream_fps", default_value="30.0"),
            Node(
                package="kuas_mechlab3",
                executable="camera_node",
                name="front_camera",
                output="screen",
                parameters=[
                    {
                        "device": front_device,
                        "frame_id": "front_camera",
                        "width": width,
                        "height": height,
                        "fps": fps,
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
                        "width": width,
                        "height": height,
                        "fps": fps,
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
                            "/front_camera/image_raw/compressed",
                            "/rear_camera/image_raw/compressed",
                        ],
                        "port": 8080,
                        "stream_fps": stream_fps,
                    }
                ],
            ),
        ]
    )
