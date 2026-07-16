"""Unit tests for the pure QR -> onboard-LED policy.

``QrLedPolicy`` decides when the onboard LED is lit for the QR task (#5): on
while a QR code is readable in front of the camera, off once it leaves view.
The policy is edge-triggered -- it reports a state only when that state
CHANGES -- so the node publishes ``led_cmd`` at transitions instead of at frame
rate, and does not stomp the cockpit's manual LED button between reads.

Time is injected so the watchdog is tested without sleeping.
"""

from kuas_mechlab3.traffic.qr_logic import DecodeThrottle, QrLedPolicy


def test_qr_read_turns_led_on() -> None:
    policy = QrLedPolicy(off_timeout_s=1.0)
    assert policy.on_qr("ML3-QR-TEST-11", now=0.0) is True


def test_no_qr_before_any_read_stays_off() -> None:
    # A tick before anything was ever decoded must not turn the LED on.
    policy = QrLedPolicy(off_timeout_s=1.0)
    assert policy.on_tick(now=0.0) is None


def test_repeated_qr_does_not_resend_on() -> None:
    # Edge-triggered: a QR held in view emits ON once, not once per frame.
    policy = QrLedPolicy(off_timeout_s=1.0)
    assert policy.on_qr("ML3-QR-TEST-11", now=0.0) is True
    assert policy.on_qr("ML3-QR-TEST-11", now=0.1) is None
    assert policy.on_qr("ML3-QR-TEST-11", now=0.2) is None


def test_qr_within_timeout_keeps_led_on() -> None:
    # Decoding is intermittent (~76% of frames), so gaps shorter than the
    # timeout must NOT flicker the LED off.
    policy = QrLedPolicy(off_timeout_s=1.0)
    assert policy.on_qr("ML3-QR-TEST-11", now=0.0) is True
    assert policy.on_tick(now=0.5) is None  # a missed frame, still within timeout
    assert policy.on_qr("ML3-QR-TEST-11", now=0.9) is None  # re-read, still on


def test_watchdog_turns_off_after_timeout() -> None:
    policy = QrLedPolicy(off_timeout_s=1.0)
    policy.on_qr("ML3-QR-TEST-11", now=0.0)
    assert policy.on_tick(now=1.2) is False


def test_watchdog_off_emitted_once() -> None:
    # Edge-triggered on the OFF side too: no repeated OFF at tick rate.
    policy = QrLedPolicy(off_timeout_s=1.0)
    policy.on_qr("ML3-QR-TEST-11", now=0.0)
    assert policy.on_tick(now=1.2) is False
    assert policy.on_tick(now=1.4) is None


def test_recovers_after_watchdog_off() -> None:
    # The full leave-then-return cycle: a later QR must light the LED again.
    policy = QrLedPolicy(off_timeout_s=1.0)
    policy.on_qr("ML3-QR-TEST-11", now=0.0)
    assert policy.on_tick(now=1.2) is False
    assert policy.on_qr("ML3-QR-TEST-11", now=1.3) is True


def test_empty_payload_is_not_a_read() -> None:
    # cv2 returns "" when it locates a QR but cannot decode it -- that is a
    # miss, not a read, and must not light the LED.
    policy = QrLedPolicy(off_timeout_s=1.0)
    assert policy.on_qr("", now=0.0) is None


def test_empty_payload_does_not_feed_the_watchdog() -> None:
    # An unreadable frame must not keep the LED alive past the timeout.
    policy = QrLedPolicy(off_timeout_s=1.0)
    policy.on_qr("ML3-QR-TEST-11", now=0.0)
    policy.on_qr("", now=0.9)  # located-not-read: must NOT refresh last-seen
    assert policy.on_tick(now=1.2) is False


def test_any_payload_counts() -> None:
    # The rule chosen is "LED on while A QR is readable" -- not tied to one
    # payload. A different code still lights it.
    policy = QrLedPolicy(off_timeout_s=1.0)
    assert policy.on_qr("SOME-OTHER-CODE", now=0.0) is True


# --- DecodeThrottle -------------------------------------------------------
# QR decoding costs ~70-105 ms/frame on the robot, and the traffic-light
# detector (#9) shares the same Pi and the same camera. #9 has a timing
# requirement (catch the green) and the QR task (#5) does not, so the QR decode
# is rate-limited to leave the detector headroom.


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
    # Defensive: the node drives this from a monotonic clock, but a negative
    # delta must not lock the decode out forever.
    throttle = DecodeThrottle(interval_s=0.2)
    throttle.should_decode(now=10.0)
    assert throttle.should_decode(now=0.0) is True
