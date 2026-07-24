"""Shared frame-rate limiter for the per-frame vision stages.

Both consumers of the front camera run a CPU-heavy stage on every incoming
frame: the QR task (#5) decodes with ``cv2.QRCodeDetector`` (~70-105 ms/frame
measured on the robot) and the traffic-light task (#9) runs YOLOv8 inference.
The camera publishes at ~30 Hz, but neither task needs anywhere near that
rate -- a traffic light changes on a seconds scale and the QR robot parks in
front of the code -- while at full rate YOLO alone saturated the Pi (~140%
CPU measured) and pushed it into thermal soft-throttling at 83 °C. Gating the
*entire* per-frame stage (JPEG decode included) to a few Hz buys that CPU
back without changing behaviour.

Time is injected (``now``) rather than read here, which keeps this module
free of ROS and testable without sleeping. Callers should pass a *monotonic*
clock: the robot's Pi has no RTC, so its wall clock jumps (~24h was observed
on a boot) once NTP corrects the restored timestamp.
"""


class DecodeThrottle:
    """Rate-limit a per-frame decode/detect stage to one run per interval.

    ``interval_s=0`` disables throttling (process every frame).
    """

    def __init__(self, interval_s: float) -> None:
        self._interval_s = interval_s
        self._last_s: float | None = None

    def should_decode(self, now: float) -> bool:
        """True when enough time has passed since the last accepted frame."""
        if self._last_s is None:
            self._last_s = now
            return True
        elapsed = now - self._last_s
        # elapsed < 0 == the clock went backwards; decode and resync rather than
        # lock the decode out until the clock catches up.
        if elapsed >= self._interval_s or elapsed < 0:
            self._last_s = now
            return True
        # NOTE: do not touch _last_s on a skip, or a 20 Hz camera would push the
        # next decode out forever.
        return False
