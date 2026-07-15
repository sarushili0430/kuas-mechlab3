"""Pure-Python policy for the auto-green LED indicator (no ROS / hardware).

Decides when the onboard LED is lit from the team-tagged traffic-light status
strings the detector publishes: on only while the team's own green light is in
view, off for red/yellow, and off shortly after the light leaves the frame (the
status topic goes silent, so a watchdog clears it). The policy is edge-triggered
-- ``on_message`` / ``on_tick`` return the new LED state only when it *changes*,
so the node drives ``led_cmd`` at transitions instead of every frame. Time is
passed in, keeping the whole thing side-effect-free and unit-testable like
``light_logic``.
"""


class LedPolicy:
    """Map traffic-light status strings to edge-triggered LED on/off decisions."""

    def __init__(self, green_token: str, off_timeout_s: float) -> None:
        """Light the LED for ``green_token`` (e.g. ``"11Green"``); drop it once no
        green has arrived for ``off_timeout_s`` seconds (the light left view)."""
        self._green_token = green_token
        self._off_timeout_s = off_timeout_s
        self._last_green_s: float | None = None
        self._state = False

    def on_message(self, data: str, now: float) -> bool | None:
        """Feed one status string at time ``now``.

        Returns the new LED state (``True``/``False``) if it changed, else
        ``None``. Our own green refreshes the on-state; any other string (red,
        yellow, another team's colour) is an explicit non-green detection that
        clears the LED at once.
        """
        if data == self._green_token:
            self._last_green_s = now
        else:
            self._last_green_s = None
        return self._evaluate(now)

    def on_tick(self, now: float) -> bool | None:
        """Watchdog step at time ``now``: return the new LED state if the last
        green has gone stale (light removed), else ``None``."""
        return self._evaluate(now)

    def _evaluate(self, now: float) -> bool | None:
        """Compute the desired state and return it only when it changes."""
        want = (
            self._last_green_s is not None
            and (now - self._last_green_s) <= self._off_timeout_s
        )
        if want != self._state:
            self._state = want
            return want
        return None
