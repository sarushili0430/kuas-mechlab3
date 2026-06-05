"""Unit tests for the pure skid-steer kinematics (no ROS / serial deps)."""

import pytest

from kuas_mechlab3.drive.kinematics import twist_to_setpoints

MAX_LINEAR = 0.5
MAX_ANGULAR = 2.0
WHEEL_SETPOINT = 10.5


def _mix(
    vx: float, wz: float, turn_sign: float = 1.0
) -> tuple[float, float, float, float]:
    """Mix a Twist with the standard ML3 limits to keep the tests terse."""
    return twist_to_setpoints(
        vx, wz, MAX_LINEAR, MAX_ANGULAR, WHEEL_SETPOINT, turn_sign
    )


def test_straight_forward_full_scale() -> None:
    assert _mix(MAX_LINEAR, 0.0) == pytest.approx((10.5,) * 4)


def test_straight_forward_half_scale() -> None:
    assert _mix(0.25, 0.0) == pytest.approx((5.25,) * 4)


def test_straight_backward() -> None:
    assert _mix(-MAX_LINEAR, 0.0) == pytest.approx((-10.5,) * 4)


def test_pure_left_turn_is_ccw() -> None:
    # REP-103: +wz spins left wheels backward, right wheels forward (CCW).
    assert _mix(0.0, MAX_ANGULAR) == pytest.approx((-10.5, -10.5, 10.5, 10.5))


def test_pure_right_turn_is_cw() -> None:
    assert _mix(0.0, -MAX_ANGULAR) == pytest.approx((10.5, 10.5, -10.5, -10.5))


def test_turn_sign_inverts_rotation() -> None:
    # turn_sign=-1 must turn the opposite way to the default +wz left turn.
    assert _mix(0.0, MAX_ANGULAR, turn_sign=-1.0) == pytest.approx(
        (10.5, 10.5, -10.5, -10.5)
    )


def test_saturation_downscales_uniformly() -> None:
    # vx and wz both full: left=0, right=2 -> scale by 2 keeps the turn ratio.
    assert _mix(MAX_LINEAR, MAX_ANGULAR) == pytest.approx((0.0, 0.0, 10.5, 10.5))


def test_input_beyond_max_is_clamped() -> None:
    # vx = 2x max_linear must saturate to the same setpoint as full scale.
    assert _mix(2 * MAX_LINEAR, 0.0) == pytest.approx((10.5,) * 4)


def test_zero_twist_is_full_stop() -> None:
    assert _mix(0.0, 0.0) == pytest.approx((0.0,) * 4)


def test_left_and_right_wheels_are_paired() -> None:
    s1, s2, s3, s4 = _mix(0.3, 0.5)
    assert s1 == s2  # FL == BL (left side)
    assert s3 == s4  # FR == BR (right side)


def test_zero_max_linear_avoids_division_by_zero() -> None:
    result = twist_to_setpoints(0.5, 0.0, 0.0, MAX_ANGULAR, WHEEL_SETPOINT)
    assert result == pytest.approx((0.0,) * 4)
