"""Pure MJPEG-over-HTTP framing for the teleop viewer (no http / cv2 deps).

Single owner of the multipart/x-mixed-replace byte format a browser <img> tag
consumes. Keeping it as byte/string functions lets the standalone pytest job
cover the framing; ``mjpeg_server`` owns the actual socket, the JPEG encoding,
and the ROS subscriptions on top of this module.
"""

BOUNDARY = "ml3frame"


def content_type(boundary: str = BOUNDARY) -> str:
    """The multipart Content-Type header value for the streaming response."""
    return f"multipart/x-mixed-replace; boundary={boundary}"


def mjpeg_part(jpeg: bytes, boundary: str = BOUNDARY) -> bytes:
    """Frame one JPEG image as a single multipart chunk for the stream."""
    head = (
        f"--{boundary}\r\n"
        f"Content-Type: image/jpeg\r\n"
        f"Content-Length: {len(jpeg)}\r\n\r\n"
    ).encode("ascii")
    return head + jpeg + b"\r\n"


def index_html(topics: list[str]) -> str:
    """A minimal page that shows every streamed topic as a live <img>."""
    figures = "\n".join(
        f"  <figure><figcaption>{t}</figcaption>"
        f'<img src="/stream?topic={t}" alt="{t}"></figure>'
        for t in topics
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        '<head><meta charset="utf-8"><title>ML3 cameras</title>\n'
        "<style>body{background:#111;color:#eee;font-family:sans-serif}"
        "figure{display:inline-block;margin:8px}"
        "img{max-width:48vw;border:1px solid #444}</style></head>\n"
        f"<body>\n<h1>ML3 cameras</h1>\n{figures}\n</body>\n</html>\n"
    )
