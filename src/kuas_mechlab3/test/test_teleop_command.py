"""Unit tests for the pure remote-teleop command translation (no ROS deps)."""

import pytest

from kuas_mechlab3.drive.teleop_command import command_to_twist, parse_command

MAX_LINEAR = 0.5
MAX_ANGULAR = 2.0


def _twist(vx: float, wz: float, deadzone: float = 0.0) -> tuple[float, float]:
    """Scale a normalised command with the standard ML3 limits (terse tests)."""
    return command_to_twist(vx, wz, MAX_LINEAR, MAX_ANGULAR, deadzone)


# -- parse_command ----------------------------------------------------------


def test_parse_command_valid() -> None:
    assert parse_command('{"vx": 0.5, "wz": -0.3}') == pytest.approx((0.5, -0.3))


def test_parse_command_ignores_extra_keys() -> None:
    parsed = parse_command('{"vx": 1.0, "wz": 0.0, "extra": 9}')
    assert parsed == pytest.approx((1.0, 0.0))


def test_parse_command_missing_key_returns_none() -> None:
    assert parse_command('{"vx": 0.5}') is None


def test_parse_command_non_numeric_returns_none() -> None:
    assert parse_command('{"vx": "fast", "wz": 0.0}') is None


def test_parse_command_null_value_returns_none() -> None:
    assert parse_command('{"vx": null, "wz": 0.0}') is None


def test_parse_command_non_finite_returns_none() -> None:
    assert parse_command('{"vx": NaN, "wz": 0.0}') is None
    assert parse_command('{"vx": Infinity, "wz": 0.0}') is None


def test_parse_command_non_object_returns_none() -> None:
    assert parse_command("[0.5, 0.3]") is None
    assert parse_command("0.5") is None


def test_parse_command_bad_json_returns_none() -> None:
    assert parse_command("{not json") is None
    assert parse_command("") is None


# -- command_to_twist -------------------------------------------------------


def test_command_to_twist_zero_is_stop() -> None:
    assert _twist(0.0, 0.0) == pytest.approx((0.0, 0.0))


def test_command_to_twist_full_forward() -> None:
    assert _twist(1.0, 0.0) == pytest.approx((0.5, 0.0))


def test_command_to_twist_full_left_turn() -> None:
    assert _twist(0.0, 1.0) == pytest.approx((0.0, 2.0))


def test_command_to_twist_half_scale() -> None:
    assert _twist(0.5, -0.5) == pytest.approx((0.25, -1.0))


def test_command_to_twist_clamps_out_of_range() -> None:
    assert _twist(2.0, -3.0) == pytest.approx((0.5, -2.0))


def test_command_to_twist_deadzone_zeroes_small_input() -> None:
    assert _twist(0.01, -0.02, deadzone=0.05) == pytest.approx((0.0, 0.0))


def test_command_to_twist_deadzone_keeps_large_input() -> None:
    assert _twist(0.2, -0.2, deadzone=0.05) == pytest.approx((0.1, -0.4))


def test_command_to_twist_default_deadzone_keeps_tiny_input() -> None:
    # default deadzone=0 must not zero a genuine small command
    assert _twist(0.01, 0.0) == pytest.approx((0.005, 0.0))
