"""Unit tests for the pure LED-indicator policy (no ROS / hardware).

``LedPolicy`` decides when the onboard LED is lit: on only while the team's green
light is in view, and edge-triggered so it emits a command only when the state
changes. Time is passed in, so the watchdog (turn the LED off shortly after the
light leaves view and the status topic goes silent) is testable without a real
clock or a ROS2 environment -- the same pure-logic split as ``light_logic``.
"""

from kuas_mechlab3.traffic.led_logic import LedPolicy


def test_green_turns_led_on() -> None:
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    assert policy.on_message("11Green", now=0.0) is True


def test_repeated_green_does_not_resend() -> None:
    # Edge-triggered: a second green while already ON emits no command.
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    policy.on_message("11Green", now=0.0)
    assert policy.on_message("11Green", now=0.2) is None


def test_yellow_turns_led_off_immediately() -> None:
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    policy.on_message("11Green", now=0.0)
    assert policy.on_message("11Yellow", now=0.1) is False


def test_red_turns_led_off_immediately() -> None:
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    policy.on_message("11Green", now=0.0)
    assert policy.on_message("11Red", now=0.1) is False


def test_non_green_while_off_is_noop() -> None:
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    assert policy.on_message("11Red", now=0.0) is None


def test_watchdog_turns_off_after_timeout_when_light_removed() -> None:
    # Light leaves view -> status topic goes silent -> only ticks arrive.
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    policy.on_message("11Green", now=0.0)
    assert policy.on_tick(now=0.9) is None  # still fresh -> stays ON
    assert policy.on_tick(now=1.2) is False  # stale -> OFF


def test_watchdog_noop_when_already_off() -> None:
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    assert policy.on_tick(now=5.0) is None


def test_green_again_after_off_turns_back_on() -> None:
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    policy.on_message("11Green", now=0.0)
    policy.on_message("11Yellow", now=0.1)  # OFF
    assert policy.on_message("11Green", now=0.2) is True


def test_fresh_green_refreshes_watchdog() -> None:
    # A new green resets the off timer; the LED must not drop on the next tick.
    policy = LedPolicy(green_token="11Green", off_timeout_s=1.0)
    policy.on_message("11Green", now=0.0)  # ON
    policy.on_message("11Green", now=0.8)  # refresh (no state change)
    assert policy.on_tick(now=1.5) is None  # 1.5 - 0.8 = 0.7 < 1.0 -> ON


def test_token_is_team_specific() -> None:
    # Only our own team's green counts; another team's green is ignored.
    policy = LedPolicy(green_token="7Green", off_timeout_s=1.0)
    assert policy.on_message("11Green", now=0.0) is None  # not our green
    assert policy.on_message("7Green", now=0.1) is True
