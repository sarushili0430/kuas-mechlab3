"""Unit tests for the pure camera frame helpers (no cv2 / ROS deps)."""

import pytest

from kuas_mechlab3.camera.frame import (
    fourcc,
    image_fields,
    image_step,
    resolve_device,
)


def test_fourcc_matches_opencv_mjpg() -> None:
    # cv2.VideoWriter_fourcc("M", "J", "P", "G") == 1196444237.
    assert fourcc("MJPG") == 1196444237


def test_fourcc_is_little_endian_packing() -> None:
    assert fourcc("\x01\x00\x00\x00") == 1
    assert fourcc("\x00\x01\x00\x00") == 256


def test_fourcc_wrong_length_raises() -> None:
    with pytest.raises(ValueError):
        fourcc("MJP")


def test_image_step_bgr8_is_three_bytes_per_pixel() -> None:
    assert image_step(640, "bgr8") == 1920


def test_image_step_mono8_is_one_byte_per_pixel() -> None:
    assert image_step(640, "mono8") == 640


def test_image_step_unsupported_encoding_raises() -> None:
    with pytest.raises(ValueError):
        image_step(640, "rgba8")


def test_image_fields_for_vga_bgr8() -> None:
    assert image_fields(480, 640) == {
        "encoding": "bgr8",
        "height": 480,
        "width": 640,
        "step": 1920,
        "is_bigendian": 0,
    }


def test_image_fields_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError):
        image_fields(0, 640)


def test_resolve_device_index_to_int() -> None:
    assert resolve_device("0") == 0
    assert isinstance(resolve_device("2"), int)


def test_resolve_device_path_stays_string() -> None:
    assert resolve_device("/dev/video0") == "/dev/video0"
