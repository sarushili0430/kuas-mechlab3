"""USB webcam capture for the ML3 forward/rear cameras (owns cv2 only).

Wraps one cv2.VideoCapture device and hands raw BGR frames upward; the per-
message arithmetic lives in ``frame`` so it stays unit-testable without a camera.
Exercised by ``colcon test`` inside the ROS2 build, not the standalone pytest
job, because it imports cv2 (which pip cannot resolve in the lint container).
"""

import cv2
import numpy as np

from kuas_mechlab3.camera.frame import fourcc, resolve_device


class CameraCapture:
    """Owns one /dev/video* device; delegates the codec tag to ``frame``."""

    def __init__(
        self,
        device: str,
        width: int,
        height: int,
        fps: float,
        codec: str = "MJPG",
    ) -> None:
        """Store the capture settings; call ``open()`` before reading frames."""
        self._device = resolve_device(device)
        self._width = width
        self._height = height
        self._fps = fps
        self._codec = codec
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        """Open the device on the V4L2 backend and request the configured format.

        The backend is pinned to V4L2 on purpose: handing a "/dev/video*" path to
        the default cv2.VideoCapture lets OpenCV pick the FFMPEG backend, which
        treats the device as a stream and blocks for *minutes* on an interrupt
        timeout before it opens. V4L2 opens a USB webcam immediately, by index or
        by path. The FOURCC must be set before width/height: at VGA+ a Logicool
        cam only reaches 30 fps over USB with MJPG, and the driver picks the
        resolution for the *current* codec, so the order matters.
        """
        cap = cv2.VideoCapture(self._device, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open camera device: {self._device!r}")
        cap.set(cv2.CAP_PROP_FOURCC, fourcc(self._codec))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        cap.set(cv2.CAP_PROP_FPS, self._fps)
        # Keep only the newest frame so teleop sees live video, not a backlog.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap

    def close(self) -> None:
        """Release the device if it is open."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    @property
    def is_open(self) -> bool:
        """Return True while the underlying device is open."""
        return self._cap is not None and bool(self._cap.isOpened())

    def read(self) -> np.ndarray | None:
        """Grab one BGR frame, or None if the grab failed (caller skips it)."""
        if self._cap is None:
            raise RuntimeError("camera device is not open")
        ok, frame = self._cap.read()
        if not ok:
            return None
        return frame
