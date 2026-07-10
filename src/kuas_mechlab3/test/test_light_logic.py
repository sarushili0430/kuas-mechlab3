from kuas_mechlab3.traffic.light_logic import classify_color, format_team_message


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
