"""Pure decision logic for the QR task's onboard LED (課題 #5).

The rule implemented here: the LED is lit while a QR code is *readable* in front
of the camera, and clears once the code leaves view. Decoding is intermittent
(measured ~76% of frames on the robot, dipping while the card rotates), so a
plain "lit on this frame's decode" rule would flicker at frame rate. Two things
prevent that:

* an **off-timeout watchdog** -- brief decode gaps keep the LED lit, and only a
  sustained absence clears it;
* **edge triggering** -- the policy reports a state only when that state
  CHANGES, so the node publishes ``led_cmd`` at transitions rather than every
  frame, and does not fight the cockpit's manual LED button between reads.

Time is injected (``now``) rather than read here, which keeps this module free
of ROS and testable without sleeping. Callers should pass a *monotonic* clock:
the robot's Pi has no RTC, so its wall clock jumps (~24h was observed on a boot)
once NTP corrects the restored timestamp, and a backwards jump would make the
watchdog's elapsed time negative and defeat it.

Note: 課題 #5 asks for a colour per QR, but the current onboard LED is a single
green on/off (see firmware ``main.cpp``: RGB is future work), so this policy is
deliberately binary -- "a QR is readable" -- not payload-dependent.
"""


class QrLedPolicy:
    """Decide the onboard LED state from QR decode events (edge-triggered)."""

    def __init__(self, off_timeout_s: float = 1.0) -> None:
        self._off_timeout_s = off_timeout_s
        self._last_read_s: float | None = None
        self._state = False

    def on_qr(self, payload: str, now: float) -> bool | None:
        """Report a decode attempt; empty ``payload`` means it was unreadable.

        cv2 returns "" when it locates a QR but cannot decode it at that angle;
        that is a miss, so it must neither light the LED nor refresh the
        watchdog.
        """
        if payload:
            self._last_read_s = now
        return self._evaluate(now)

    def on_tick(self, now: float) -> bool | None:
        """Advance time with no decode, letting the watchdog clear the LED."""
        return self._evaluate(now)

    def _evaluate(self, now: float) -> bool | None:
        """Compute the desired state and return it only when it changes."""
        want = (
            self._last_read_s is not None
            and (now - self._last_read_s) <= self._off_timeout_s
        )
        if want != self._state:
            self._state = want
            return want
        return None
