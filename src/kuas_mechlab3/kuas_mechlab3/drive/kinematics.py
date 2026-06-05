"""Pure skid-steer kinematics: a Twist (vx, wz) -> four wheel setpoints.

Owns the robot-geometry responsibility only -- it knows nothing about ROS,
serial ports, or the wire protocol, so the mixing is a side-effect-free function
the standalone pytest job can cover without a ROS2 environment.
"""

from kuas_mechlab3.utils import clamp


def twist_to_setpoints(
    vx: float,
    wz: float,
    max_linear: float,
    max_angular: float,
    wheel_setpoint: float,
    turn_sign: float = 1.0,
) -> tuple[float, float, float, float]:
    """Mix a Twist into four wheel setpoints (s1=FL, s2=BL, s3=FR, s4=BR).

    vx / wz are normalised against max_linear / max_angular, combined as a
    differential-drive pair (left = lin - ang, right = lin + ang), then scaled
    down uniformly if either side saturates so the straight-line ratio is kept.

    Sign follows REP-103: +wz is counter-clockwise (a left turn). Pass
    turn_sign=-1.0 if the robot turns the wrong way on the bench.
    """
    lin = clamp(vx / max_linear, -1.0, 1.0) if max_linear else 0.0
    ang = clamp(wz / max_angular, -1.0, 1.0) if max_angular else 0.0
    ang *= turn_sign

    left = lin - ang
    right = lin + ang

    # Uniform down-scale keeps the turn ratio when a side would saturate.
    scale = max(1.0, abs(left), abs(right))
    left /= scale
    right /= scale

    s_left = left * wheel_setpoint
    s_right = right * wheel_setpoint
    # s1 FL and s2 BL share the left side; s3 FR and s4 BR share the right side.
    return (s_left, s_left, s_right, s_right)
