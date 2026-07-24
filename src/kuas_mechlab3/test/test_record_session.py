"""Unit tests for the RecordingSession lifecycle (fake runner / clock; no ROS).

The ``ros2 bag record`` subprocess is replaced by a FakeRunner so the sequencing
-- indexing, meta writing, discard, the state-machine guards -- is exercised
without a sourced ROS2 environment (the same pure/IO split the repo uses).
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kuas_mechlab3.record_session import (
    AlreadyRecording,
    BagHandle,
    NotRecording,
    RecordingSession,
)
from kuas_mechlab3.recording import default_topics


class FakeHandle:
    """A stand-in for the bag subprocess handle; records that it was stopped."""

    def __init__(self) -> None:
        self.stopped = False

    def poll(self) -> int | None:
        return 0 if self.stopped else None

    def send_signal(self, sig: int) -> None:
        self.stopped = True

    def wait(self, timeout: float | None = None) -> int:
        return 0

    def terminate(self) -> None:
        self.stopped = True


class FakeRunner:
    """Capture start/stop calls instead of spawning ros2 bag record."""

    def __init__(self) -> None:
        self.started: list[tuple[Path, list[str], str]] = []
        self.handles: list[FakeHandle] = []

    def start(self, bag_dir: Path, topics: list[str], storage: str) -> FakeHandle:
        self.started.append((bag_dir, list(topics), storage))
        handle = FakeHandle()
        self.handles.append(handle)
        return handle

    def stop(self, handle: BagHandle) -> None:
        # send_signal is part of the BagHandle protocol; FakeHandle marks itself
        # stopped so a test can assert the recorder was told to finalise.
        handle.send_signal(0)


class FakeClock:
    """A monotonically advancing clock so started/stopped stamps are distinct."""

    def __init__(self) -> None:
        self._t = datetime(2026, 7, 3, 12, 0, 0)

    def __call__(self) -> datetime:
        self._t += timedelta(seconds=5)
        return self._t


def _session(tmp_path: Path, runner: FakeRunner) -> RecordingSession:
    return RecordingSession(
        out_root=tmp_path,
        route="route_a",
        operator="koyu",
        topics=default_topics(),
        start_index=1,
        ros_domain_id=11,
        runner=runner,
        now=FakeClock(),
    )


# -- start ------------------------------------------------------------------


def test_start_launches_bag_and_reports_recording(tmp_path: Path) -> None:
    runner = FakeRunner()
    session = _session(tmp_path, runner)

    status = session.start()

    assert session.is_recording is True
    assert status["recording"] is True
    assert status["index"] == 1
    assert status["episode"] == status["episode"]  # a real dir name was assigned
    bag_dir, topics, storage = runner.started[0]
    assert bag_dir.name == "bag"
    assert storage == "sqlite3"
    assert "/cmd_norm" in topics


def test_start_twice_raises(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    session.start()
    with pytest.raises(AlreadyRecording):
        session.start()


def test_start_overrides_route_and_topics(tmp_path: Path) -> None:
    runner = FakeRunner()
    session = _session(tmp_path, runner)
    session.start(route="loop_1", operator="mai", topics=["/cmd_norm"])
    _, topics, _ = runner.started[0]
    assert topics == ["/cmd_norm"]
    assert session.status()["route"] == "loop_1"
    assert session.status()["operator"] == "mai"


# -- stop / finalize --------------------------------------------------------


def test_stop_writes_meta_and_advances_index(tmp_path: Path) -> None:
    runner = FakeRunner()
    session = _session(tmp_path, runner)
    started = session.start()
    res = session.stop(label="success", notes="clear")

    assert session.is_recording is False
    assert res["recording"] is False
    assert res["saved"] == started["episode"]
    assert res["label"] == "success"
    assert res["duration_s"] > 0
    assert runner.handles[0].stopped is True

    meta_path = tmp_path / started["episode"] / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["label"] == "success"
    assert meta["notes"] == "clear"
    assert meta["episode_index"] == 1
    assert meta["ros_domain_id"] == 11

    assert session.index == 2  # advanced after a saved episode


def test_two_phase_stop_matches_one_shot(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    session.start()
    session.stop_bag()
    assert session.is_recording is False  # bag closed, meta still pending
    res = session.finalize(label="failure", notes="")
    assert res["label"] == "failure"
    assert session.index == 2


def test_stop_without_recording_raises(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    with pytest.raises(NotRecording):
        session.stop(label="success")


# -- discard ----------------------------------------------------------------


def test_discard_removes_dir_and_reuses_index(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    started = session.start()
    res = session.discard()

    assert res["discarded"] is True
    assert not (tmp_path / started["episode"]).exists()
    assert session.is_recording is False
    assert session.index == 1  # index reused, not advanced


def test_discard_without_recording_raises(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    with pytest.raises(NotRecording):
        session.discard()


# -- finalize_unlabeled (Ctrl-C / shutdown) ---------------------------------


def test_finalize_unlabeled_saves_in_flight(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    started = session.start()
    res = session.finalize_unlabeled(notes="interrupted")

    assert res is not None
    assert res["label"] == "unlabeled"
    meta = json.loads(
        (tmp_path / started["episode"] / "meta.json").read_text(encoding="utf-8")
    )
    assert meta["label"] == "unlabeled"
    assert meta["notes"] == "interrupted"


def test_finalize_unlabeled_when_idle_returns_none(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    assert session.finalize_unlabeled() is None


# -- status ------------------------------------------------------------------


def test_status_when_idle(tmp_path: Path) -> None:
    session = _session(tmp_path, FakeRunner())
    status = session.status()
    assert status["recording"] is False
    assert status["episode"] is None
    assert status["index"] == 1
    assert status["route"] == "route_a"
