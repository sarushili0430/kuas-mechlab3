"""Unit tests for the pure camera helpers (no cv2 / ROS deps)."""

import pytest

from kuas_mechlab3.camera.frame import fourcc, resolve_device


def test_fourcc_matches_opencv_mjpg() -> None:
    # cv2.VideoWriter_fourcc("M", "J", "P", "G") == 1196444237.
    assert fourcc("MJPG") == 1196444237


def test_fourcc_is_little_endian_packing() -> None:
    assert fourcc("\x01\x00\x00\x00") == 1
    assert fourcc("\x00\x01\x00\x00") == 256


def test_fourcc_wrong_length_raises() -> None:
    with pytest.raises(ValueError):
        fourcc("MJP")


def test_resolve_device_index_to_int() -> None:
    assert resolve_device("0") == 0
    assert isinstance(resolve_device("2"), int)


def test_resolve_device_path_stays_string() -> None:
    assert resolve_device("/dev/video0") == "/dev/video0"
