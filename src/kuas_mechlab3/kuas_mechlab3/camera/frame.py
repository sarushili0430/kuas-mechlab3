"""Pure helpers for the ML3 webcams: FOURCC packing and device id resolution.

No cv2 / rclpy here, so the standalone pytest job covers the easy-to-get-wrong
bits (the FOURCC bit-packing, index-vs-path handling) without a camera device or
a sourced ROS2 environment. ``capture`` owns the cv2 device on top of these.
"""


def fourcc(code: str) -> int:
    """Pack a 4-char codec tag (e.g. "MJPG") into OpenCV's FOURCC integer.

    Mirrors cv2.VideoWriter_fourcc without importing cv2, so the codec the
    capture layer requests -- MJPG keeps the USB bandwidth sane -- is
    unit-testable on its own. OpenCV packs the four bytes little-endian.
    """
    if len(code) != 4:
        raise ValueError("FOURCC code must be exactly 4 characters")
    return sum(ord(c) << (8 * i) for i, c in enumerate(code))


def resolve_device(value: str) -> int | str:
    """Turn a device parameter into the argument cv2.VideoCapture expects.

    A bare number ("0") selects /dev/video0 by index; anything else is treated
    as a path ("/dev/v4l/by-id/...-video-index0"), which is the stable way to
    keep "front" and "rear" from swapping across reboots.
    """
    return int(value) if value.isdigit() else value
