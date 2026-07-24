"""Unit tests for the pure mbed wire protocol (no serial deps)."""

from kuas_mechlab3.drive.protocol import (
    SERVO_MAX_US,
    SERVO_MIN_US,
    angle_to_us,
    format_led,
    format_servo_us,
    format_setpoints,
    parse_led_echo,
    parse_servo_echo,
    parse_telemetry,
)


def test_format_setpoints_two_decimals_and_eop() -> None:
    assert format_setpoints(10.5, 10.5, 0.0, 0.0) == "10.50/10.50/0.00/0.00/d"


def test_format_setpoints_handles_negatives() -> None:
    assert format_setpoints(-1.5, 2.0, -3.25, 4.0) == "-1.50/2.00/-3.25/4.00/d"


def test_format_setpoints_rounds_to_two_decimals() -> None:
    assert format_setpoints(1.234, 0.0, 0.0, 0.0) == "1.23/0.00/0.00/0.00/d"


def test_parse_telemetry_valid_line() -> None:
    line = "sp 1.0 2.0 3.0 4.0 | rpm 0.0 0.0 0.0 0.0 | pwm 1500 -1500 0 750"
    assert parse_telemetry(line) == {
        "sp": [1.0, 2.0, 3.0, 4.0],
        "rpm": [0.0, 0.0, 0.0, 0.0],
        "pwm": [1500, -1500, 0, 750],
    }


def test_parse_telemetry_pwm_stays_int() -> None:
    result = parse_telemetry("sp 0 0 0 0 | rpm 0 0 0 0 | pwm 1 2 3 4")
    assert result is not None
    assert all(isinstance(v, int) for v in result["pwm"])


def test_parse_telemetry_missing_rpm_returns_none() -> None:
    assert parse_telemetry("sp 1.0 | pwm 1 2 3 4") is None


def test_parse_telemetry_missing_pwm_returns_none() -> None:
    assert parse_telemetry("sp 1.0 | rpm 1.0") is None


def test_parse_telemetry_malformed_numbers_returns_none() -> None:
    assert parse_telemetry("sp x y z | rpm 0 0 0 0 | pwm 1 2 3 4") is None


def test_parse_telemetry_non_telemetry_line_returns_none() -> None:
    assert parse_telemetry("hello world") is None


# --- servo packet -----------------------------------------------------------


def test_format_servo_us_basic() -> None:
    assert format_servo_us(1500, 1800) == "1500/1800/a"


def test_format_servo_us_clamps_below_and_above_band() -> None:
    assert format_servo_us(100, 9000) == f"{SERVO_MIN_US}/{SERVO_MAX_US}/a"


def test_format_servo_us_coerces_float_to_int() -> None:
    assert format_servo_us(1500.9, 1499.1) == "1500/1499/a"


def test_angle_to_us_default_range_endpoints_and_mid() -> None:
    assert angle_to_us(0.0) == SERVO_MIN_US
    assert angle_to_us(180.0) == SERVO_MAX_US
    assert angle_to_us(90.0) == 1500


def test_angle_to_us_clamps_out_of_range_angles() -> None:
    assert angle_to_us(-30.0) == SERVO_MIN_US
    assert angle_to_us(999.0) == SERVO_MAX_US


def test_angle_to_us_custom_span() -> None:
    # 135 deg over a 0..270 span is the midpoint -> the pulse-band midpoint.
    assert angle_to_us(135.0, 0.0, 270.0, 500, 2500) == 1500


def test_angle_to_us_degenerate_span_maps_to_min() -> None:
    assert angle_to_us(42.0, 90.0, 90.0) == SERVO_MIN_US


def test_parse_servo_echo_valid() -> None:
    assert parse_servo_echo("srv 1500 1800") == (1500, 1800)


def test_parse_servo_echo_ignores_telemetry_line() -> None:
    line = "sp 0 0 0 0 | rpm 0 0 0 0 | pwm 0 0 0 0"
    assert parse_servo_echo(line) is None


def test_parse_servo_echo_malformed_returns_none() -> None:
    assert parse_servo_echo("srv x y") is None


def test_telemetry_and_servo_parsers_are_mutually_exclusive() -> None:
    # The drive telemetry line must never be mistaken for a servo ack, and a
    # servo ack must never be mistaken for telemetry -- this is what keeps the
    # shared serial stream non-breaking.
    assert parse_servo_echo("sp 1 2 3 4 | rpm 0 0 0 0 | pwm 1 2 3 4") is None
    assert parse_telemetry("srv 1500 1800") is None


# --- LED packet -------------------------------------------------------------


def test_format_led_on() -> None:
    assert format_led(True) == "1/l"


def test_format_led_off() -> None:
    assert format_led(False) == "0/l"


def test_parse_led_echo_on() -> None:
    assert parse_led_echo("led 1") is True


def test_parse_led_echo_off() -> None:
    assert parse_led_echo("led 0") is False


def test_parse_led_echo_ignores_telemetry_line() -> None:
    assert parse_led_echo("sp 0 0 0 0 | rpm 0 0 0 0 | pwm 0 0 0 0") is None


def test_parse_led_echo_ignores_servo_ack() -> None:
    assert parse_led_echo("srv 1500 1800") is None


def test_parse_led_echo_malformed_returns_none() -> None:
    assert parse_led_echo("led x") is None


def test_led_echo_not_mistaken_for_telemetry_or_servo() -> None:
    # The LED ack must never be misread by the two parsers that share the serial
    # stream (keeps drive telemetry + servo acks non-breaking).
    assert parse_telemetry("led 1") is None
    assert parse_servo_echo("led 1") is None
