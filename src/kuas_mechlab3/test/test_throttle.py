"""Unit tests for the shared frame throttle (QR task #5 and traffic task #9).

Heavy per-frame stages (QR decode ~70-105 ms/frame, YOLO inference) cannot run
at the camera's 30 Hz on the shared Pi; ``DecodeThrottle`` gates them to a few
Hz. Time is injected so the tests run without sleeping.
"""

from kuas_mechlab3.traffic.throttle import DecodeThrottle


def test_first_frame_always_decodes() -> None:
    throttle = DecodeThrottle(interval_s=0.2)
    assert throttle.should_decode(now=0.0) is True


def test_frame_within_interval_is_skipped() -> None:
    throttle = DecodeThrottle(interval_s=0.2)
    throttle.should_decode(now=0.0)
    assert throttle.should_decode(now=0.1) is False


def test_frame_after_interval_decodes() -> None:
    throttle = DecodeThrottle(interval_s=0.2)
    throttle.should_decode(now=0.0)
    assert throttle.should_decode(now=0.2) is True


def test_skipped_frames_do_not_reset_the_clock() -> None:
    # A skip must not push the next decode further out, or a 20 Hz camera would
    # starve the decode entirely.
    throttle = DecodeThrottle(interval_s=0.2)
    throttle.should_decode(now=0.0)  # decode
    throttle.should_decode(now=0.05)  # skip
    throttle.should_decode(now=0.1)  # skip
    assert throttle.should_decode(now=0.2) is True


def test_zero_interval_decodes_every_frame() -> None:
    # interval 0 disables throttling (the pre-throttle behaviour).
    throttle = DecodeThrottle(interval_s=0.0)
    assert throttle.should_decode(now=0.0) is True
    assert throttle.should_decode(now=0.0) is True


def test_backwards_time_does_not_wedge_the_throttle() -> None:
    # Defensive: the nodes drive this from a monotonic clock, but a negative
    # delta must not lock the decode out forever.
    throttle = DecodeThrottle(interval_s=0.2)
    throttle.should_decode(now=10.0)
    assert throttle.should_decode(now=0.0) is True
