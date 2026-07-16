"""Unit tests for the pure remote-teleop command translation (no ROS deps)."""

import pytest

from kuas_mechlab3.drive.teleop_command import (
    command_to_norm,
    command_to_twist,
    parse_command,
    parse_led_command,
    parse_servo_command,
)

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


# -- command_to_norm --------------------------------------------------------


def test_command_to_norm_passes_through_in_range() -> None:
    assert command_to_norm(0.5, -0.3) == pytest.approx((0.5, -0.3))


def test_command_to_norm_clamps_out_of_range() -> None:
    assert command_to_norm(2.0, -3.0) == pytest.approx((1.0, -1.0))


def test_command_to_norm_keeps_small_input_no_deadzone() -> None:
    # the action label is the raw intent; deadzone is a downstream safety filter
    assert command_to_norm(0.01, -0.02) == pytest.approx((0.01, -0.02))


def test_command_to_norm_zero_is_zero() -> None:
    assert command_to_norm(0.0, 0.0) == pytest.approx((0.0, 0.0))


# -- parse_servo_command ----------------------------------------------------


def test_parse_servo_command_valid() -> None:
    assert parse_servo_command('{"servo": [30, 120]}') == pytest.approx((30.0, 120.0))


def test_parse_servo_command_accepts_floats() -> None:
    assert parse_servo_command('{"servo": [30.5, 119.9]}') == pytest.approx(
        (30.5, 119.9)
    )


def test_parse_servo_command_missing_key_returns_none() -> None:
    assert parse_servo_command('{"vx": 0.5, "wz": 0.0}') is None


def test_parse_servo_command_wrong_length_returns_none() -> None:
    assert parse_servo_command('{"servo": [30]}') is None
    assert parse_servo_command('{"servo": [1, 2, 3]}') is None


def test_parse_servo_command_non_list_returns_none() -> None:
    assert parse_servo_command('{"servo": 30}') is None


def test_parse_servo_command_non_numeric_returns_none() -> None:
    assert parse_servo_command('{"servo": ["a", "b"]}') is None


def test_parse_servo_command_non_finite_returns_none() -> None:
    assert parse_servo_command('{"servo": [NaN, 0]}') is None


def test_parse_servo_command_bad_json_returns_none() -> None:
    assert parse_servo_command("{not json") is None
    assert parse_servo_command("") is None


def test_parse_servo_command_non_object_returns_none() -> None:
    assert parse_servo_command("[30, 120]") is None


# -- parse_led_command ------------------------------------------------------


def test_parse_led_command_true() -> None:
    assert parse_led_command('{"led": true}') is True


def test_parse_led_command_false() -> None:
    assert parse_led_command('{"led": false}') is False


def test_parse_led_command_accepts_int_0_1() -> None:
    assert parse_led_command('{"led": 1}') is True
    assert parse_led_command('{"led": 0}') is False


def test_parse_led_command_missing_key_returns_none() -> None:
    assert parse_led_command('{"vx": 0.5, "wz": 0.0}') is None


def test_parse_led_command_non_bool_returns_none() -> None:
    assert parse_led_command('{"led": "on"}') is None
    assert parse_led_command('{"led": 2}') is None


def test_parse_led_command_bad_json_returns_none() -> None:
    assert parse_led_command("{not json") is None


# -- command dispatch is mutually exclusive ---------------------------------


def test_drive_servo_led_parsers_are_mutually_exclusive() -> None:
    # teleop_server tries each parser in turn; a message must match exactly one,
    # so the drive path stays non-breaking when servo/LED messages arrive.
    assert parse_command('{"servo": [30, 120]}') is None
    assert parse_command('{"led": true}') is None
    assert parse_servo_command('{"vx": 0.5, "wz": 0.0}') is None
    assert parse_servo_command('{"led": true}') is None
    assert parse_led_command('{"vx": 0.5, "wz": 0.0}') is None
    assert parse_led_command('{"servo": [30, 120]}') is None
