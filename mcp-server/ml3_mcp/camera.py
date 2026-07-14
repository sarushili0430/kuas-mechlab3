"""Fetch a single still frame from the robot's MJPEG server (port 8080).

The stream is ``multipart/x-mixed-replace`` with boundary ``ml3frame``; each
part is a standalone JPEG carrying a ``Content-Length`` header (camera/mjpeg.py).
There is no single-frame endpoint, so we open the stream, read until one
complete part is available, and return its JPEG bytes."""
from __future__ import annotations

import httpx

BOUNDARY = b"ml3frame"
_MAX_BYTES = 8 * 1024 * 1024


class CameraError(RuntimeError):
    pass


def _parse_content_length(header_blob: bytes) -> int | None:
    for line in header_blob.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            try:
                return int(line.split(b":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _extract_by_jpeg_markers(buf: bytes, offset: int) -> bytes | None:
    soi = buf.find(b"\xff\xd8", offset)
    if soi == -1:
        return None
    eoi = buf.find(b"\xff\xd9", soi + 2)
    if eoi == -1:
        return None
    return bytes(buf[soi : eoi + 2])


def extract_first_jpeg(buf: bytes) -> bytes | None:
    """Return the first complete JPEG in an MJPEG buffer, or None if more bytes
    are still needed. Uses ``Content-Length`` when present, else SOI/EOI markers."""
    start = buf.find(b"--" + BOUNDARY)
    if start == -1:
        # No boundary seen yet; try a bare JPEG in case of an odd stream.
        return _extract_by_jpeg_markers(buf, 0)
    header_end = buf.find(b"\r\n\r\n", start)
    if header_end == -1:
        return None
    content_length = _parse_content_length(bytes(buf[start:header_end]))
    body_start = header_end + 4
    if content_length is None:
        return _extract_by_jpeg_markers(buf, body_start)
    body_end = body_start + content_length
    if len(buf) < body_end:
        return None
    return bytes(buf[body_start:body_end])


async def fetch_frame(stream_url: str, *, timeout: float = 10.0) -> bytes:
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", stream_url) as resp:
            if resp.status_code != 200:
                raise CameraError(f"camera stream returned HTTP {resp.status_code}")
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                frame = extract_first_jpeg(buf)
                if frame is not None:
                    return frame
                if len(buf) > _MAX_BYTES:
                    raise CameraError("no complete MJPEG frame early in the stream")
    raise CameraError("stream ended before a complete frame was received")
