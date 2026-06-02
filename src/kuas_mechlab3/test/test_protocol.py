"""Unit tests for the pure mbed wire protocol (no serial deps)."""

from kuas_mechlab3.drive.protocol import format_setpoints, parse_telemetry


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
