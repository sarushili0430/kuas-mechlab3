from ml3_mcp import camera

JPEG = b"\xff\xd8\xff\xe0-jpeg-body-\xff\xd9"


def _part(jpeg: bytes) -> bytes:
    return (
        b"--ml3frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
        + str(len(jpeg)).encode()
        + b"\r\n\r\n"
        + jpeg
        + b"\r\n"
    )


def test_extract_full_part():
    assert camera.extract_first_jpeg(_part(JPEG)) == JPEG


def test_needs_more_bytes_returns_none():
    assert camera.extract_first_jpeg(_part(JPEG)[:20]) is None


def test_extract_across_two_chunks():
    full = _part(JPEG)
    assert camera.extract_first_jpeg(full[:15]) is None
    assert camera.extract_first_jpeg(full[:15] + full[15:]) == JPEG


def test_content_length_parse():
    assert camera._parse_content_length(b"--ml3frame\r\nContent-Length: 42") == 42
    assert (
        camera._parse_content_length(b"--ml3frame\r\nContent-Type: image/jpeg") is None
    )


def test_jpeg_marker_fallback_without_boundary():
    buf = b"garbage\xff\xd8body\xff\xd9tail"
    assert camera.extract_first_jpeg(buf) == b"\xff\xd8body\xff\xd9"
