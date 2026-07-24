"""Unit tests for the pure MJPEG-over-HTTP framing (no http / cv2 deps)."""

from kuas_mechlab3.camera.mjpeg import content_type, index_html, mjpeg_part


def test_content_type_carries_the_boundary() -> None:
    assert content_type("b") == "multipart/x-mixed-replace; boundary=b"


def test_mjpeg_part_wraps_jpeg_with_headers_and_length() -> None:
    part = mjpeg_part(b"\xff\xd8jpeg", boundary="b")
    assert part.startswith(b"--b\r\n")
    assert b"Content-Type: image/jpeg\r\n" in part
    assert b"Content-Length: 6\r\n" in part  # len(b"\xff\xd8jpeg") == 6
    assert part.endswith(b"\r\n")
    assert b"\xff\xd8jpeg" in part


def test_index_html_lists_every_topic_as_a_stream_img() -> None:
    topics = ["/front_camera/image_raw", "/rear_camera/image_raw"]
    html = index_html(topics)
    assert html.count("<img") == 2
    for topic in topics:
        assert f"/stream?topic={topic}" in html
