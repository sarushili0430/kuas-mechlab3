"""Launch the recording-control HTTP API (record_server).

Brings up record_server, which exposes start / stop / discard / status of
``ros2 bag record`` over HTTP so the cockpit's REC button can flag an
imitation-learning episode's begin and end without a Pi terminal -- the remote
counterpart of the interactive ``scripts/record_episodes.py``. Run it alongside
the driver, cameras, and teleop (so /cmd_norm + the camera topics exist to
record):

    ros2 launch kuas_mechlab3 record_launch.py route:=route_a operator:=koyu

Then flag episodes from the cockpit (or any HTTP client):

    curl -X POST http://<pi>:9002/record/start
    curl -X POST http://<pi>:9002/record/stop -d '{"label":"success"}'
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Bring up the HTTP -> ros2 bag recording-control server."""
    host = LaunchConfiguration("host")
    # ParameterValue pins the type so the string launch args reach the typed node
    # parameters as int/bool (a bare substitution would stay a string).
    port = ParameterValue(LaunchConfiguration("port"), value_type=int)
    out = LaunchConfiguration("out")
    route = LaunchConfiguration("route")
    operator = LaunchConfiguration("operator")
    storage = LaunchConfiguration("storage")
    include_rear = ParameterValue(LaunchConfiguration("include_rear"), value_type=bool)
    include_state = ParameterValue(
        LaunchConfiguration("include_state"), value_type=bool
    )
    start_index = ParameterValue(LaunchConfiguration("start_index"), value_type=int)

    return LaunchDescription(
        [
            DeclareLaunchArgument("host", default_value="0.0.0.0"),
            DeclareLaunchArgument("port", default_value="9002"),
            DeclareLaunchArgument("out", default_value="datasets/raw"),
            DeclareLaunchArgument("route", default_value="route_a"),
            DeclareLaunchArgument("operator", default_value="unknown"),
            DeclareLaunchArgument("storage", default_value="sqlite3"),
            DeclareLaunchArgument("include_rear", default_value="true"),
            DeclareLaunchArgument("include_state", default_value="true"),
            DeclareLaunchArgument("start_index", default_value="1"),
            Node(
                package="kuas_mechlab3",
                executable="record_server",
                name="record_server",
                output="screen",
                parameters=[
                    {
                        "host": host,
                        "port": port,
                        "out": out,
                        "route": route,
                        "operator": operator,
                        "storage": storage,
                        "include_rear": include_rear,
                        "include_state": include_state,
                        "start_index": start_index,
                    }
                ],
            ),
        ]
    )
