"""Pure wire protocol for the ML3 mbed drivetrain firmware (no serial deps).

Single owner of the byte-level format. The firmware (firmware/robot/src/main.cpp):

  * accepts setpoint packets  "s1/s2/s3/s4/d"  (4 floats, '/'-separated, 'd' EOP)
  * emits telemetry lines      "sp .. | rpm .. | pwm .."

Keeping these as string<->data functions lets the standalone pytest job cover
them; SerialLink owns the actual port I/O on top of this module.
"""

from typing import TypedDict

EOP = "d"


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
