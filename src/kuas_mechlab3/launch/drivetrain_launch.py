"""Launch the mbed_driver node with default parameters.

teleop_keyboard is intentionally NOT launched here: it needs an interactive
terminal (tty), so run it on its own in a separate shell:

    ros2 run kuas_mechlab3 teleop_keyboard

or publish cmd_vel from teleop_twist_keyboard / nav2 instead.
"""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Bring up the Twist->serial driver."""
    return LaunchDescription(
        [
            Node(
                package="kuas_mechlab3",
                executable="mbed_driver",
                name="mbed_driver",
                output="screen",
                parameters=[
                    {
                        "port": "/dev/ttyACM0",
                        "baud": 115200,
                        "max_linear": 0.5,
                        "max_angular": 2.0,
                        "wheel_setpoint": 10.5,
                        "turn_sign": 1.0,
                        "cmd_timeout": 0.4,
                        # Servo (arm) angle->pulse calibration; DS3225 on TIM15.
                        "servo_min_us": 500,
                        "servo_max_us": 2500,
                        "servo_min_deg": 0.0,
                        "servo_max_deg": 180.0,
                    }
                ],
            ),
        ]
    )
