"""Shared IO for one recorded episode: the ros2 bag subprocess + meta sidecar.

The single owner of "run ``ros2 bag record`` for one episode and write its
``meta.json``", reused by both recorders:

* ``scripts/record_episodes.py`` -- the interactive, stdin-driven recorder, run
  in a terminal on the Pi (Enter to start/stop, ``d`` to discard).
* ``kuas_mechlab3.episode_recorder`` -- the ROS node driven remotely over
  ``RECORD_TOPIC``, so the operator can start/stop from the teleop cockpit.

Kept apart from the pure ``kuas_mechlab3.recording`` (which owns the dataset
layout / metadata *schema* and stays import-clean so the standalone pytest job
covers it) because these helpers touch subprocess / signals / the filesystem --
the same pure-vs-IO split as ``teleop_command`` (pure) vs. ``teleop_server``
(node). There is nothing ROS-specific here beyond invoking the ``ros2`` CLI, so
neither recorder needs to duplicate the bag plumbing.
"""

import json
import signal
import subprocess
from pathlib import Path
from typing import Any


def start_bag(
    bag_dir: Path, topics: list[str], storage: str
) -> "subprocess.Popen[bytes]":
    """Launch ``ros2 bag record`` into bag_dir in its own session.

    ``start_new_session`` detaches it from the terminal's Ctrl-C so the caller
    alone controls its lifecycle (a clean SIGINT lets rosbag2 finalise the bag).
    """
    cmd = ["ros2", "bag", "record", "-o", str(bag_dir), "-s", storage, *topics]
    return subprocess.Popen(cmd, start_new_session=True)


def stop_bag(proc: "subprocess.Popen[bytes]") -> None:
    """SIGINT the recorder so rosbag2 closes the bag cleanly, then wait it out."""
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)


def write_meta(ep_dir: Path, meta: dict[str, Any]) -> None:
    """Write the episode metadata sidecar (meta.json) next to its bag."""
    (ep_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
