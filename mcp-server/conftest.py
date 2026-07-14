"""Shared pytest fixtures. Placed at the project root so `mock_robot` (which is
not part of the installed package) is importable and so its directory is on
sys.path for the test session."""
import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import pytest  # noqa: E402

from mock_robot import MockRobot  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def mock_robot():
    robot = MockRobot(
        host="127.0.0.1",
        ws_port=_free_port(),
        cam_port=_free_port(),
        rec_port=_free_port(),
    )
    robot.start()
    try:
        yield robot
    finally:
        robot.stop()
