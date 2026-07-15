"""Launch the traffic-light detector for the ML3 barrier task.

Subscribes to the front camera's CompressedImage topic (published by camera_node
/ cameras_launch) -- it does NOT open the /dev/video* device, so it runs
alongside cameras_launch / start-all.sh without contending for the webcam. When
it sees a green light it publishes "<team>Green" (e.g. "11Green") to
traffic_light_topic, the string the on-field barrier opens for:

    ros2 launch kuas_mechlab3 traffic_launch.py team_number:=11 \\
        image_topic:=/front_camera/image_raw/compressed

Also brings up ``led_indicator``, which lights the onboard LED (``led_cmd``)
while that green light is in view -- a local visual confirmation of the
detection; ``off_timeout`` clears the LED once the light leaves the frame.

Needs a camera publishing frames (cameras_launch or a camera_node) and the
ultralytics pip package (`pip install ultralytics`; downloads yolov8n.pt on the
first run, so pre-fetch it before an offline competition boot).
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Bring up the traffic-light detector and the onboard-LED indicator."""
    # ParameterValue pins the type so the string launch args reach the typed
    # node parameters as int/float (a bare substitution would stay a string).
    team_number = ParameterValue(LaunchConfiguration("team_number"), value_type=int)
    image_topic = LaunchConfiguration("image_topic")
    imgsz = ParameterValue(LaunchConfiguration("imgsz"), value_type=int)
    off_timeout = ParameterValue(LaunchConfiguration("off_timeout"), value_type=float)

    return LaunchDescription(
        [
            DeclareLaunchArgument("team_number", default_value="11"),
            DeclareLaunchArgument(
                "image_topic",
                default_value="/front_camera/image_raw/compressed",
            ),
            DeclareLaunchArgument("imgsz", default_value="256"),
            DeclareLaunchArgument("off_timeout", default_value="1.0"),
            Node(
                package="kuas_mechlab3",
                executable="traffic_light",
                name="traffic_light_node",
                output="screen",
                parameters=[
                    {
                        "team_number": team_number,
                        "image_topic": image_topic,
                        "imgsz": imgsz,
                    }
                ],
            ),
            Node(
                package="kuas_mechlab3",
                executable="led_indicator",
                name="led_indicator",
                output="screen",
                parameters=[
                    {
                        "team_number": team_number,
                        "off_timeout": off_timeout,
                    }
                ],
            ),
        ]
    )
