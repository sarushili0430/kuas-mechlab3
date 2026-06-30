"""Launch the remote-controlled episode recorder (episode_recorder).

Brings up episode_recorder, which records one ros2 bag per demo on start/stop
commands the operator sends from the teleop cockpit (relayed by teleop_server on
``/record_cmd``). It is the unattended, network-driven counterpart of the
interactive ``scripts/record_episodes.py`` (stdin) -- so data acquisition can be
started and ended from the same cockpit you steer from, with no terminal on the
Pi. Run it alongside drivetrain_launch.py (driver), cameras_launch.py (video),
and teleop_launch.py (the WebSocket bridge that relays the record commands):

    ros2 launch kuas_mechlab3 record_launch.py route:=route_a operator:=koyu

Episodes land in ``<out>/<timestamp>_<route>_NNN/`` (default ``datasets/raw``,
resolved against the current directory -- run from the repo root). ``route`` /
``operator`` here are the defaults; a cockpit ``start`` may override them
per-episode. Recorded topics follow ``recording.default_topics`` (action +
camera(s) + optional state); drop the rear camera / state with
``include_rear:=false`` / ``include_state:=false``.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description() -> LaunchDescription:
    """Bring up the /record_cmd -> ros2 bag episode recorder."""
    route = LaunchConfiguration("route")
    operator = LaunchConfiguration("operator")
    out = LaunchConfiguration("out")
    storage = LaunchConfiguration("storage")
    # ParameterValue pins the type so the string launch args reach the typed node
    # parameters as bool/int (a bare substitution would stay a string).
    include_rear = ParameterValue(LaunchConfiguration("include_rear"), value_type=bool)
    include_state = ParameterValue(
        LaunchConfiguration("include_state"), value_type=bool
    )
    start_index = ParameterValue(LaunchConfiguration("start_index"), value_type=int)

    return LaunchDescription(
        [
            DeclareLaunchArgument("route", default_value="route_a"),
            DeclareLaunchArgument("operator", default_value="unknown"),
            DeclareLaunchArgument("out", default_value="datasets/raw"),
            DeclareLaunchArgument("storage", default_value="sqlite3"),
            DeclareLaunchArgument("include_rear", default_value="true"),
            DeclareLaunchArgument("include_state", default_value="true"),
            DeclareLaunchArgument("start_index", default_value="1"),
            Node(
                package="kuas_mechlab3",
                executable="episode_recorder",
                name="episode_recorder",
                output="screen",
                parameters=[
                    {
                        "route": route,
                        "operator": operator,
                        "out": out,
                        "storage": storage,
                        "include_rear": include_rear,
                        "include_state": include_state,
                        "start_index": start_index,
                    }
                ],
            ),
        ]
    )
