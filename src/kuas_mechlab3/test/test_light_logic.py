from kuas_mechlab3.traffic.light_logic import (
    classify_color,
    format_team_message,
    status_message,
)


def test_classify_red_dominant() -> None:
    assert classify_color(100, 10, 5) == "red"


def test_classify_green_dominant() -> None:
    assert classify_color(10, 100, 5) == "green"


def test_classify_yellow_dominant() -> None:
    assert classify_color(5, 10, 100) == "yellow"


def test_classify_tie_is_unknown() -> None:
    assert classify_color(50, 50, 10) == "unknown"


def test_classify_all_zero_is_unknown() -> None:
    assert classify_color(0, 0, 0) == "unknown"


def test_format_team_message_green() -> None:
    # The barrier opens for this exact string when team 11 sees green.
    assert format_team_message(11, "green") == "11Green"


def test_format_team_message_red() -> None:
    assert format_team_message(11, "red") == "11Red"


def test_format_team_message_other_team() -> None:
    assert format_team_message(12, "yellow") == "12Yellow"


# --- status_message: the node's publish (output IO) contract -----------------


def test_status_message_detected_green_is_team_green() -> None:
    # The exact string the barrier opens for when team 11 sees green.
    assert status_message(True, 5, 100, 5, 11) == "11Green"


def test_status_message_detected_red() -> None:
    assert status_message(True, 100, 5, 5, 11) == "11Red"


def test_status_message_detected_yellow_other_team() -> None:
    assert status_message(True, 5, 5, 100, 12) == "12Yellow"


def test_status_message_not_detected_is_none() -> None:
    # No traffic light in view -> publish nothing, even if a colour dominates.
    assert status_message(False, 5, 100, 5, 11) is None


def test_status_message_detected_but_ambiguous_is_none() -> None:
    # Detected, but a colour tie is "unknown" -> stay quiet.
    assert status_message(True, 50, 50, 10, 11) is None


def test_status_message_detected_all_zero_is_none() -> None:
    assert status_message(True, 0, 0, 0, 11) is None
