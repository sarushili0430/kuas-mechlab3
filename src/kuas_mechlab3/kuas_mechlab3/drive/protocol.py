"""Pure wire protocol for the ML3 mbed drivetrain firmware (no serial deps).

Single owner of the byte-level format. The firmware (firmware/robot/src/main.cpp):

  * accepts setpoint packets  "s1/s2/s3/s4/d"  (4 floats, '/'-separated, 'd' EOP)
  * accepts servo packets      "us1/us2/a"     (2 ints [µs], '/'-separated, 'a' EOP)
  * accepts LED packets        "v/l"           (1 int 0|1, 'l' EOP)
  * emits telemetry lines      "sp .. | rpm .. | pwm .."
  * emits a servo ack          "srv us1 us2"   (only right after a servo packet)
  * emits an LED ack           "led v"         (only right after an LED packet)

The drive, servo, and LED packets share the port but use distinct end-of-packet
bytes ('d' / 'a' / 'l'), so the firmware parses them independently and the servo
and LED paths leave the 4-wheel format untouched. Keeping these as string<->data
functions lets the standalone pytest job cover them; SerialLink owns the actual
port I/O on top of this module.
"""

from typing import TypedDict

EOP = "d"

# --- Servo (arm) packet: pulse widths in microseconds, distinct 'a' terminator.
SERVO_EOP = "a"
SERVO_MIN_US = 500  # hard safety band, mirrored by the firmware's own clamp
SERVO_MAX_US = 2500

# --- LED packet: on/off (1|0), distinct 'l' terminator; firmware echoes "led v".
LED_EOP = "l"


class Telemetry(TypedDict):
    """One parsed telemetry line: setpoints, measured rpm, and applied pwm."""

    sp: list[float]
    rpm: list[float]
    pwm: list[int]


def format_setpoints(s1: float, s2: float, s3: float, s4: float) -> str:
    """Build one "s1/s2/s3/s4/d" packet (2 decimals, 'd' end-of-packet)."""
    return f"{s1:.2f}/{s2:.2f}/{s3:.2f}/{s4:.2f}/{EOP}"


def parse_telemetry(line: str) -> Telemetry | None:
    """Parse "sp .. | rpm .. | pwm .." into a Telemetry dict.

    Returns None for any line that is not a well-formed telemetry line (missing
    a field, or non-numeric values), so callers can simply skip it.
    """
    if "rpm" not in line or "pwm" not in line:
        return None
    try:
        sp = [float(x) for x in line.split("sp")[1].split("|")[0].split()]
        rpm = [float(x) for x in line.split("rpm")[1].split("|")[0].split()]
        pwm = [int(x) for x in line.split("pwm")[1].split()]
    except (IndexError, ValueError):
        return None
    return {"sp": sp, "rpm": rpm, "pwm": pwm}


def _clamp_us(us: int) -> int:
    """Saturate a pulse width to the [SERVO_MIN_US, SERVO_MAX_US] safety band."""
    return max(SERVO_MIN_US, min(SERVO_MAX_US, us))


def format_servo_us(us1: float, us2: float) -> str:
    """Build one "us1/us2/a" servo packet (pulse widths in µs, 'a' end-of-packet).

    Each width is truncated to a whole microsecond and clamped to
    [SERVO_MIN_US, SERVO_MAX_US] -- the same safe band the firmware enforces --
    so a caller can never emit a pulse that drives a DS3225 past its mechanical
    stops. Separate from ``format_setpoints`` ('d' EOP); the firmware parses the
    two independently, so the 4-wheel drive format is unaffected.
    """
    return f"{_clamp_us(int(us1))}/{_clamp_us(int(us2))}/{SERVO_EOP}"


def angle_to_us(
    angle_deg: float,
    min_deg: float = 0.0,
    max_deg: float = 180.0,
    min_us: int = SERVO_MIN_US,
    max_us: int = SERVO_MAX_US,
) -> int:
    """Map a joint angle in degrees to a servo pulse width in µs (linear, clamped).

    ``angle_deg`` is clamped to [min_deg, max_deg], linearly mapped onto
    [min_us, max_us], rounded to the nearest microsecond, then saturated to the
    absolute [SERVO_MIN_US, SERVO_MAX_US] safety band. Keeping this calibration on
    the Pi lets the per-servo angle span be tuned without reflashing the firmware.
    A degenerate min_deg == max_deg maps everything to min_us.
    """
    if max_deg == min_deg:
        return _clamp_us(min_us)
    clamped = max(min_deg, min(max_deg, angle_deg))
    frac = (clamped - min_deg) / (max_deg - min_deg)
    return _clamp_us(round(min_us + frac * (max_us - min_us)))


def parse_servo_echo(line: str) -> tuple[int, int] | None:
    """Parse a firmware servo ack "srv us1 us2" into (us1, us2), else None.

    Returns None for any line that is not a well-formed servo ack -- including
    every telemetry line, which never contains "srv" -- so callers can skip it
    exactly like ``parse_telemetry`` skips non-telemetry lines.
    """
    if "srv" not in line:
        return None
    try:
        parts = line.split("srv")[1].split()
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None


def format_led(on: bool) -> str:
    """Build one "v/l" LED packet (v=1 on / 0 off, 'l' end-of-packet).

    Separate from the drive and servo formats; the firmware parses it on its own
    'l' terminator, so neither the 4-wheel drive format nor the servo format is
    affected.
    """
    return f"{1 if on else 0}/{LED_EOP}"


def parse_led_echo(line: str) -> bool | None:
    """Parse a firmware LED ack "led v" into True/False, else None.

    Returns None for any line that is not a well-formed LED ack -- including every
    telemetry line and servo ack, neither of which contains "led" -- so callers
    can skip it exactly like ``parse_telemetry`` skips non-telemetry lines.
    """
    if "led" not in line:
        return None
    try:
        return int(line.split("led")[1].split()[0]) != 0
    except (IndexError, ValueError):
        return None
