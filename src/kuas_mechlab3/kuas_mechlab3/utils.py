"""Pure-Python helpers with no ROS dependencies.

Logic placed here can be unit-tested by the standalone pytest job without a
sourced ROS2 environment. Code that imports ``rclpy`` (nodes, etc.) should be
covered by ``colcon test`` inside the ROS2 build workflow instead.
"""


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp ``value`` into the inclusive range ``[lower, upper]``.

    Raises:
        ValueError: if ``lower`` is greater than ``upper``.
    """
    if lower > upper:
        raise ValueError("lower must not be greater than upper")
    return max(lower, min(value, upper))
