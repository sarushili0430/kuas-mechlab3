"""Pure-Python traffic-light logic with no ROS / OpenCV dependencies.

The colour classification takes already-counted colour-mask pixel totals (the
OpenCV masking itself lives in the node), so both the decision and the
team-tagged message format are side-effect-free functions the standalone pytest
job can cover without a ROS2 environment or a camera.
"""


def classify_color(red_pixels: int, green_pixels: int, yellow_pixels: int) -> str:
    """Return the dominant light colour from three colour-mask pixel counts.

    The colour with the strictly largest count wins. A tie -- including the
    all-zero "no light in view" case -- is reported as ``"unknown"`` so the
    caller can decline to publish a status it is not sure about.
    """
    if red_pixels > green_pixels and red_pixels > yellow_pixels:
        return "red"
    if green_pixels > red_pixels and green_pixels > yellow_pixels:
        return "green"
    if yellow_pixels > red_pixels and yellow_pixels > green_pixels:
        return "yellow"
    return "unknown"


def format_team_message(team_number: int, color: str) -> str:
    """Format the on-field message for a detected colour, e.g. ``"11Green"``.

    The barrier opens only for the exact string ``f"{team}Green"`` (ML3 brief),
    so team 11 seeing green must send ``"11Green"``. The colour is capitalised
    to match that ``<team><Color>`` contract.
    """
    return f"{team_number}{color.capitalize()}"


def status_message(
    detected: bool,
    red_pixels: int,
    green_pixels: int,
    yellow_pixels: int,
    team_number: int,
) -> str | None:
    """The exact string to publish for one frame, or ``None`` to stay quiet.

    This is the node's output IO contract in one pure, testable place: it ties
    the detection gate to the colour decision and the wire format. Nothing is
    published unless a traffic light is actually in view *and* a definite colour
    won -- a frame with no light, or an ambiguous ``"unknown"``, returns ``None``
    (the node publishes nothing) rather than a misleading status. Otherwise the
    team-tagged ``<team><Color>`` string is returned; a detected green light for
    team 11 gives ``"11Green"`` -- the string the barrier opens for.
    """
    if not detected:
        return None
    color = classify_color(red_pixels, green_pixels, yellow_pixels)
    if color == "unknown":
        return None
    return format_team_message(team_number, color)
