"""Pure-Python traffic-light logic with no ROS / OpenCV dependencies.

The colour classification takes already-counted colour-mask pixel totals (the
OpenCV masking itself lives in the node), so both the decision and the
team-tagged message format are side-effect-free functions the standalone pytest
job can cover without a ROS2 environment or a camera. The HSV colour table and
the detection-box clipping live here too: they are plain data / arithmetic, and
they are exactly the parts that were wrong when red and yellow were being
reported as the same colour.
"""

# One HSV bound as (hue, saturation, value); OpenCV hue is 0..179.
HsvBound = tuple[int, int, int]

# Colour-mask segments per lamp, as (low, high) inRange pairs.
#
# * Red wraps hue 0, so it needs TWO segments (0..10 and 170..179) -- masking
#   only 0..10 misses half of the red glow and lets yellow win on a red lamp.
# * Hue 11..17 (orange) is deliberately assigned to NEITHER red nor yellow: an
#   overexposed red LED reads orange-ish, and claiming that band for either
#   colour is how red and yellow get confused. Ambiguous pixels count nowhere,
#   and classify_color's tie rule then keeps the node quiet.
# * The saturation/value floors exclude the blown-out white LED core (low S)
#   and the dark housing/background (low V) from every mask.
#
# Initial values are LED-typical; calibrate against journalctl output from the
# node's debug:=true parameter if the field light reads differently.
HSV_SEGMENTS: dict[str, tuple[tuple[HsvBound, HsvBound], ...]] = {
    "red": (
        ((0, 100, 90), (10, 255, 255)),
        ((170, 100, 90), (179, 255, 255)),
    ),
    "yellow": (((18, 100, 90), (35, 255, 255)),),
    "green": (((45, 80, 90), (95, 255, 255)),),
}


def clip_box(
    x1: float, y1: float, x2: float, y2: float, width: int, height: int
) -> tuple[int, int, int, int] | None:
    """Clamp a detection box to the frame, or None if nothing usable remains.

    YOLO boxes are floats and may poke past the frame edge; the colour masks
    must count pixels inside the detected traffic light only (not the whole
    frame, where the background outvotes the lamp), so the node crops the frame
    to this clipped box before masking.
    """
    ix1, iy1 = max(0, int(x1)), max(0, int(y1))
    ix2, iy2 = min(width, int(x2)), min(height, int(y2))
    if ix2 - ix1 < 1 or iy2 - iy1 < 1:
        return None
    return ix1, iy1, ix2, iy2


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
