"""Pure frame helpers for the ML3 webcams: FOURCC, Image fields, device id.

No cv2 / rclpy / numpy here, so the standalone pytest job covers the bits that
are easy to get subtly wrong (the row stride and the FOURCC bit-packing) without
a camera device or a sourced ROS2 environment. ``capture`` owns the cv2 device
and ``camera_node`` owns the sensor_msgs/Image publisher on top of these helpers.
"""

from typing import TypedDict

# Bytes per pixel for the encodings a Logicool USB webcam realistically emits.
_CHANNELS = {"bgr8": 3, "rgb8": 3, "mono8": 1}


class ImageFields(TypedDict):
    """The scalar sensor_msgs/Image fields derived from one packed frame."""

    encoding: str
    height: int
    width: int
    step: int
    is_bigendian: int


def fourcc(code: str) -> int:
    """Pack a 4-char codec tag (e.g. "MJPG") into OpenCV's FOURCC integer.

    Mirrors cv2.VideoWriter_fourcc without importing cv2, so the codec the
    capture layer requests -- MJPG keeps the USB bandwidth sane at 720p/30 --
    is unit-testable on its own. OpenCV packs the four bytes little-endian.
    """
    if len(code) != 4:
        raise ValueError("FOURCC code must be exactly 4 characters")
    return sum(ord(c) << (8 * i) for i, c in enumerate(code))


def image_step(width: int, encoding: str = "bgr8") -> int:
    """Full row stride in bytes for a packed (un-padded) frame."""
    try:
        channels = _CHANNELS[encoding]
    except KeyError:
        raise ValueError(f"unsupported encoding: {encoding}") from None
    return width * channels


def image_fields(height: int, width: int, encoding: str = "bgr8") -> ImageFields:
    """Derive the sensor_msgs/Image scalar fields for a packed frame.

    The node fills these onto the Image message and attaches ``frame.tobytes()``
    as the payload; keeping the stride arithmetic here means a wrong step is
    caught by pytest instead of showing up as a skewed image on the robot.
    """
    if height <= 0 or width <= 0:
        raise ValueError("height and width must be positive")
    return {
        "encoding": encoding,
        "height": height,
        "width": width,
        "step": image_step(width, encoding),
        "is_bigendian": 0,
    }


def resolve_device(value: str) -> int | str:
    """Turn a device parameter into the argument cv2.VideoCapture expects.

    A bare number ("0") selects /dev/video0 by index; anything else is treated
    as a path ("/dev/v4l/by-id/...-video-index0"), which is the stable way to
    keep "front" and "rear" from swapping across reboots.
    """
    return int(value) if value.isdigit() else value
