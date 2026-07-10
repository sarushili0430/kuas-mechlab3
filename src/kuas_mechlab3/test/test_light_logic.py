from itertools import combinations

from kuas_mechlab3.traffic.light_logic import (
    HSV_SEGMENTS,
    classify_color,
    clip_box,
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


# --- HSV_SEGMENTS: the colour-mask table that separates red from yellow ------


def test_red_covers_both_hue_ends() -> None:
    # OpenCV red wraps hue 0: without the 170..179 segment a red lamp's glow
    # is half-missed and yellow can outvote it.
    hues = [(low[0], high[0]) for low, high in HSV_SEGMENTS["red"]]
    assert any(lo == 0 for lo, _ in hues)
    assert any(hi == 179 for _, hi in hues)


def test_colour_hue_ranges_do_not_overlap() -> None:
    # A hue claimed by two colours is how one lamp gets reported as another.
    for a, b in combinations(HSV_SEGMENTS, 2):
        for a_low, a_high in HSV_SEGMENTS[a]:
            for b_low, b_high in HSV_SEGMENTS[b]:
                assert a_high[0] < b_low[0] or b_high[0] < a_low[0]


def test_orange_band_belongs_to_no_colour() -> None:
    # An overexposed red LED reads orange (hue ~11..17); that band must count
    # toward neither red nor yellow so an ambiguous glow stays "unknown".
    for segments in HSV_SEGMENTS.values():
        for low, high in segments:
            assert high[0] < 11 or low[0] > 17


def test_all_segments_exclude_white_core_and_dark_background() -> None:
    # Saturation floor rejects the blown-out white LED core; value floor
    # rejects the dark housing. Without them every colour counts junk pixels.
    for segments in HSV_SEGMENTS.values():
        for low, _high in segments:
            assert low[1] >= 80  # saturation floor
            assert low[2] >= 80  # value floor


# --- clip_box: crop the frame to the detected light before masking -----------


def test_clip_box_inside_frame() -> None:
    assert clip_box(10.4, 20.9, 100.2, 200.7, 320, 240) == (10, 20, 100, 200)


def test_clip_box_clamps_to_frame_edges() -> None:
    assert clip_box(-5.0, -5.0, 400.0, 300.0, 320, 240) == (0, 0, 320, 240)


def test_clip_box_degenerate_is_none() -> None:
    assert clip_box(50.0, 60.0, 50.5, 200.0, 320, 240) is None


def test_clip_box_fully_outside_is_none() -> None:
    assert clip_box(400.0, 300.0, 500.0, 400.0, 320, 240) is None
