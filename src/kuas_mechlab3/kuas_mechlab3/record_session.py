"""Owns one dataset run's ``ros2 bag record`` lifecycle (IO; DI-testable).

The single place that turns "start / stop / discard an episode" into a running
``ros2 bag record`` subprocess plus the on-disk episode directory and its
``meta.json``. Two drivers sit on top of it and share this sequencing: the
interactive CLI ``scripts/record_episodes.py`` (keyboard) and the
``record_server`` node (HTTP from the cockpit) -- so start/stop behaves the same
whether flagged from the Pi terminal or a phone.

Responsibility split: the dataset layout and metadata *schema* stay in the pure
``recording`` module and the wire *payloads* in the pure ``record_control``
module; this class only sequences the subprocess and the filesystem and guards
the state machine. The bag subprocess is injected (``runner``) so the sequencing
-- indexing, meta writing, discard, the already/not-recording guards -- is unit
testable without a sourced ROS2 environment; the default runner shells out to
``ros2 bag record``.

Stop is two-phase on purpose: ``stop_bag`` finalises the bag the instant the run
ends (so no idle tail is recorded while the operator picks a label), then
``finalize`` writes the labelled ``meta.json``. The one-shot ``stop`` composes
both under a single lock for the HTTP caller, which already knows the label.
"""

import json
import shutil
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Protocol

from kuas_mechlab3.record_control import (
    discarded_payload,
    status_payload,
    stopped_payload,
)
from kuas_mechlab3.recording import build_metadata, episode_dirname


class AlreadyRecording(RuntimeError):
    """Raised when ``start`` is called while an episode is already recording."""


class NotRecording(RuntimeError):
    """Raised when ``stop`` / ``discard`` is called with nothing recording."""


class BagHandle(Protocol):
    """The minimal handle a runner returns; ``subprocess.Popen`` satisfies it."""

    def poll(self) -> int | None:
        """Return the exit code, or None while the recorder is still running."""

    def send_signal(self, sig: int) -> None:
        """Deliver ``sig`` to the recorder process."""

    def wait(self, timeout: float | None = None) -> int:
        """Block until the recorder exits (or ``timeout`` elapses)."""

    def terminate(self) -> None:
        """Force-terminate the recorder (SIGTERM)."""


class Runner(Protocol):
    """Starts / stops a bag recorder; ``BagRunner`` is the real implementation.

    Typed structurally so a test double (no ROS) satisfies it without inheriting
    -- the seam that keeps the session's sequencing unit-testable.
    """

    def start(self, bag_dir: Path, topics: list[str], storage: str) -> BagHandle:
        """Begin recording ``topics`` into ``bag_dir`` and return a handle."""

    def stop(self, handle: BagHandle) -> None:
        """Finalise the recorder ``handle`` cleanly."""


class BagRunner:
    """Default runner: spawn / stop a real ``ros2 bag record`` subprocess.

    Split out from the session so tests can inject a fake and exercise the
    indexing / meta / discard logic without ROS. Mirrors the subprocess handling
    the interactive recorder used to own inline.
    """

    def start(self, bag_dir: Path, topics: list[str], storage: str) -> BagHandle:
        """Launch ``ros2 bag record`` into ``bag_dir`` in its own session.

        ``start_new_session`` detaches it from the terminal's Ctrl-C so this
        process alone controls its lifecycle (a clean SIGINT lets rosbag2
        finalise the bag).
        """
        cmd = ["ros2", "bag", "record", "-o", str(bag_dir), "-s", storage, *topics]
        return subprocess.Popen(cmd, start_new_session=True)

    def stop(self, handle: BagHandle) -> None:
        """SIGINT the recorder so rosbag2 closes the bag cleanly, then wait."""
        if handle.poll() is None:
            handle.send_signal(signal.SIGINT)
            try:
                handle.wait(timeout=10)
            except subprocess.TimeoutExpired:
                handle.terminate()
                handle.wait(timeout=5)


class RecordingSession:
    """Sequence bag start / stop / discard for one dataset run (thread-safe).

    State machine, guarded by a re-entrant lock so the HTTP server's worker
    threads can call concurrently:

        idle --start--> recording --stop_bag--> pending --finalize--> idle
                              \\--------- discard ---------> idle

    ``recording`` = a bag subprocess is running; ``pending`` = the bag is closed
    but its labelled ``meta.json`` has not been written yet (the CLI window while
    the operator types a label). The episode index advances only on a saved
    finalize -- a discard reuses the number.
    """

    def __init__(
        self,
        *,
        out_root: Path,
        route: str,
        operator: str,
        topics: list[str],
        storage: str = "sqlite3",
        start_index: int = 1,
        ros_domain_id: int | None = None,
        runner: Runner | None = None,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        """Configure the run's defaults; nothing is recorded until ``start``."""
        self._out_root = out_root
        self._route = route
        self._operator = operator
        self._topics = topics
        self._storage = storage
        self._index = start_index
        self._ros_domain_id = ros_domain_id
        self._runner: Runner = runner or BagRunner()
        self._now = now

        self._lock = RLock()
        self._handle: BagHandle | None = None
        self._ep_dir: Path | None = None
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        # The route / operator / topics actually used by the in-flight episode
        # (a start request may override the run defaults per episode).
        self._cur_route = route
        self._cur_operator = operator
        self._cur_topics = topics

    @property
    def is_recording(self) -> bool:
        """True while a bag subprocess is running."""
        with self._lock:
            return self._handle is not None

    @property
    def index(self) -> int:
        """The index the next started episode will use."""
        with self._lock:
            return self._index

    def start(
        self,
        *,
        route: str | None = None,
        operator: str | None = None,
        topics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Begin recording a new episode; return its status payload.

        Any of route / operator / topics may override the run defaults for this
        episode alone. Raises ``AlreadyRecording`` if one is already in flight.
        """
        with self._lock:
            if self._handle is not None:
                raise AlreadyRecording("an episode is already recording")
            self._cur_route = route or self._route
            self._cur_operator = operator or self._operator
            self._cur_topics = topics or self._topics
            self._started_at = self._now()
            self._stopped_at = None
            name = episode_dirname(self._started_at, self._cur_route, self._index)
            self._ep_dir = self._out_root / name
            self._ep_dir.mkdir(parents=True, exist_ok=True)
            self._handle = self._runner.start(
                self._ep_dir / "bag", self._cur_topics, self._storage
            )
            return self._status_locked()

    def stop_bag(self) -> None:
        """Finalise the bag now (phase 1 of stop); leave meta for ``finalize``.

        Raises ``NotRecording`` if nothing is recording. Idempotent-safe: the
        bag is closed and its stop time frozen, so a slow label prompt does not
        record an idle tail.
        """
        with self._lock:
            if self._handle is None:
                raise NotRecording("nothing is recording")
            self._runner.stop(self._handle)
            self._handle = None
            self._stopped_at = self._now()

    def finalize(self, *, label: str, notes: str = "") -> dict[str, Any]:
        """Write the labelled ``meta.json`` for the stopped bag (phase 2 of stop).

        Advances the episode index and returns the stopped payload. Raises
        ``NotRecording`` if there is no stopped-but-unfinalised episode.
        """
        with self._lock:
            return self._finalize_locked(label=label, notes=notes)

    def stop(self, *, label: str, notes: str = "") -> dict[str, Any]:
        """One-shot stop for a caller that already has the label (the HTTP API).

        Composes ``stop_bag`` + ``finalize`` under a single lock so no other
        thread can slip between the two phases.
        """
        with self._lock:
            self.stop_bag()
            return self._finalize_locked(label=label, notes=notes)

    def discard(self) -> dict[str, Any]:
        """Stop (if running) and delete the current episode; reuse its index.

        Works from either ``recording`` or ``pending``. Raises ``NotRecording``
        if there is no episode to drop.
        """
        with self._lock:
            if self._handle is None and self._ep_dir is None:
                raise NotRecording("nothing is recording")
            if self._handle is not None:
                self._runner.stop(self._handle)
                self._handle = None
            ep_dir = self._ep_dir
            assert ep_dir is not None  # guaranteed by the guard above
            name = ep_dir.name
            shutil.rmtree(ep_dir, ignore_errors=True)
            self._clear_locked()
            # Index is deliberately NOT advanced: the dropped number is reused.
            return discarded_payload(episode=name, index=self._index)

    def finalize_unlabeled(self, notes: str = "interrupted") -> dict[str, Any] | None:
        """Save any in-flight / pending episode as ``unlabeled`` (never lose data).

        For Ctrl-C in the CLI and for server shutdown: a long demo is kept
        (relabel later) rather than thrown away. Returns None if idle.
        """
        with self._lock:
            if self._handle is not None:
                self.stop_bag()
            if self._ep_dir is None:
                return None
            return self._finalize_locked(label="unlabeled", notes=notes)

    def status(self) -> dict[str, Any]:
        """Return the current recording status payload (thread-safe snapshot)."""
        with self._lock:
            return self._status_locked()

    # -- internals (call with the lock held) --------------------------------

    def _finalize_locked(self, *, label: str, notes: str) -> dict[str, Any]:
        """Write meta.json for the pending episode and advance the index."""
        if self._ep_dir is None or self._started_at is None:
            raise NotRecording("no episode to finalize")
        stopped = self._stopped_at or self._now()
        meta = build_metadata(
            route=self._cur_route,
            operator=self._cur_operator,
            index=self._index,
            started_at=self._started_at,
            stopped_at=stopped,
            label=label,
            notes=notes,
            topics=self._cur_topics,
            bag_dir="bag",
            ros_domain_id=self._ros_domain_id,
        )
        (self._ep_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        payload = stopped_payload(
            saved=self._ep_dir.name,
            index=self._index,
            label=str(meta["label"]),
            notes=notes,
            duration_s=float(meta["duration_s"]),
        )
        self._clear_locked()
        self._index += 1
        return payload

    def _clear_locked(self) -> None:
        """Drop all in-flight episode state (back to idle)."""
        self._handle = None
        self._ep_dir = None
        self._started_at = None
        self._stopped_at = None

    def _status_locked(self) -> dict[str, Any]:
        """Build the status payload from current state (lock held)."""
        recording = self._handle is not None
        return status_payload(
            recording=recording,
            index=self._index,
            episode=self._ep_dir.name if self._ep_dir is not None else None,
            started_at=(
                self._started_at.isoformat(timespec="seconds")
                if self._started_at is not None
                else None
            ),
            route=self._cur_route if self._ep_dir is not None else self._route,
            operator=self._cur_operator if self._ep_dir is not None else self._operator,
        )
