"""Launch the remote WebSocket teleop bridge (teleop_server).

Brings up teleop_server, which accepts JSON drive commands over a WebSocket and
republishes them as cmd_vel Twist for the mbed_driver -- the remote counterpart
of teleop_keyboard (which needs a local tty and is run separately). Unlike
teleop_keyboard this needs no tty, so it is safe to launch. Run it alongside
drivetrain_launch.py (the driver) and cameras_launch.py (the video feed):

    ros2 launch kuas_mechlab3 teleop_launch.py port:=9001 max_linear:=0.5

Then drive it from the bundled client (or any WebSocket sender):

    ros2 run kuas_mechlab3 teleop_ws_client --url ws://localhost:9001
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Bring up the WebSocket -> cmd_vel teleop bridge."""
    host = LaunchConfiguration("host")
    # ParameterValue pins the type so the string launch args reach the typed node
    # parameters as int/float (a bare substitution would stay a string).
    port = ParameterValue(LaunchConfiguration("port"), value_type=int)
    publish_rate = ParameterValue(LaunchConfiguration("publish_rate"), value_type=float)
    hold_timeout = ParameterValue(LaunchConfiguration("hold_timeout"), value_type=float)
    max_linear = ParameterValue(LaunchConfiguration("max_linear"), value_type=float)
    max_angular = ParameterValue(LaunchConfiguration("max_angular"), value_type=float)
    deadzone = ParameterValue(LaunchConfiguration("deadzone"), value_type=float)

    return LaunchDescription(
        [
            DeclareLaunchArgument("host", default_value="0.0.0.0"),
            DeclareLaunchArgument("port", default_value="9001"),
            DeclareLaunchArgument("publish_rate", default_value="20.0"),
            DeclareLaunchArgument("hold_timeout", default_value="0.4"),
            DeclareLaunchArgument("max_linear", default_value="0.5"),
            DeclareLaunchArgument("max_angular", default_value="2.0"),
            DeclareLaunchArgument("deadzone", default_value="0.05"),
            Node(
                package="kuas_mechlab3",
                executable="teleop_server",
                name="teleop_server",
                output="screen",
                parameters=[
                    {
                        "host": host,
                        "port": port,
                        "publish_rate": publish_rate,
                        "hold_timeout": hold_timeout,
                        "max_linear": max_linear,
                        "max_angular": max_angular,
                        "deadzone": deadzone,
                    }
                ],
            ),
        ]
    )
