"""ROS2 node: drive episode recording from RECORD_TOPIC (remote teleop control).

The topic-driven sibling of ``scripts/record_episodes.py``. Where that script is
driven by stdin (Enter to start/stop, in a terminal on the Pi), this node is
driven by ``RECORD_TOPIC`` -- the start / stop / discard command the operator
sends over the teleop WebSocket, which ``teleop_server`` relays into the ROS
graph. So data acquisition can be started and ended from the same cockpit the
operator steers from, with no terminal on the robot. This node is to
``record_episodes.py`` what ``teleop_server`` (remote WS) is to
``teleop_keyboard`` (local tty).

Responsibility split (repo policy): the on-disk layout / metadata schema is the
pure ``kuas_mechlab3.recording``; the ``ros2 bag`` subprocess + ``meta.json`` IO
is ``kuas_mechlab3.episode_session`` (shared with the stdin recorder); this node
owns only the subscription and the per-episode lifecycle. One bag at a time: a
``start`` while already recording, or a ``stop`` / ``discard`` while idle, is
logged and ignored. On shutdown an in-flight run is finalised as ``unlabeled``
so a long demo is never thrown away (the operator can relabel it later).

A ``stop`` carries the success/failure label from the cockpit; a ``stop`` with no
label is saved as ``unlabeled`` (never silently ``success``), matching the
dataset's "only success trains" rule.
"""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from kuas_mechlab3.episode_session import start_bag, stop_bag, write_meta
from kuas_mechlab3.recording import (
    RECORD_TOPIC,
    RecordCommand,
    build_metadata,
    default_topics,
    episode_dirname,
    format_duration,
    parse_record_command,
)


class EpisodeRecorder(Node):  # type: ignore[misc]
    """Start/stop/discard one ros2 bag per episode on remote record commands."""

    def __init__(self) -> None:
        """Declare parameters, prepare the output dir, subscribe to RECORD_TOPIC."""
        super().__init__("episode_recorder")

        self.declare_parameter("route", "route_a")
        self.declare_parameter("operator", os.environ.get("USER", "unknown"))
        self.declare_parameter("out", "datasets/raw")
        self.declare_parameter("include_rear", True)
        self.declare_parameter("include_state", True)
        self.declare_parameter("storage", "sqlite3")
        self.declare_parameter("start_index", 1)

        self._route = str(self.get_parameter("route").value)
        self._operator = str(self.get_parameter("operator").value)
        self._out_root = Path(str(self.get_parameter("out").value)).expanduser()
        self._storage = str(self.get_parameter("storage").value)
        self._topics = default_topics(
            include_rear=bool(self.get_parameter("include_rear").value),
            include_state=bool(self.get_parameter("include_state").value),
        )
        self._index = int(self.get_parameter("start_index").value)

        domain = os.environ.get("ROS_DOMAIN_ID")
        self._domain_id = int(domain) if domain and domain.isdigit() else None

        # In-flight episode state -- all None / cleared when idle.
        self._proc: "subprocess.Popen[bytes] | None" = None
        self._ep_dir: Path | None = None
        self._started: datetime | None = None
        self._cur_route = self._route
        self._cur_operator = self._operator

        self._out_root.mkdir(parents=True, exist_ok=True)
        self._sub = self.create_subscription(String, RECORD_TOPIC, self._on_command, 10)

        self.get_logger().info(
            f"episode_recorder up: {RECORD_TOPIC} -> {self._out_root}  "
            f"(route={self._route}, operator={self._operator}); "
            f"topics: {', '.join(self._topics)}"
        )

    def _on_command(self, msg: String) -> None:
        """Dispatch one relayed record command (start / stop / discard)."""
        cmd = parse_record_command(msg.data)
        if cmd is None:
            self.get_logger().warn(f"ignored malformed record command: {msg.data!r}")
            return
        if cmd.action == "start":
            self._start(cmd)
        elif cmd.action == "stop":
            self._stop(cmd)
        else:  # "discard" -- the only remaining valid action
            self._discard()

    def _start(self, cmd: RecordCommand) -> None:
        """Open a new episode directory and start ros2 bag (no-op if recording)."""
        if self._proc is not None:
            self.get_logger().warn("already recording; ignoring start")
            return
        self._cur_route = cmd.route or self._route
        self._cur_operator = cmd.operator or self._operator
        self._started = datetime.now()
        self._ep_dir = self._out_root / episode_dirname(
            self._started, self._cur_route, self._index
        )
        self._ep_dir.mkdir(parents=True, exist_ok=True)
        self._proc = start_bag(self._ep_dir / "bag", self._topics, self._storage)
        self.get_logger().info(
            f"● REC start ep {self._index:03d} -> {self._ep_dir.name}"
        )

    def _stop(self, cmd: RecordCommand) -> None:
        """Finalise the bag and write meta.json with the command's label."""
        if self._proc is None or self._ep_dir is None or self._started is None:
            self.get_logger().warn("not recording; ignoring stop")
            return
        stop_bag(self._proc)
        stopped = datetime.now()
        dur = format_duration((stopped - self._started).total_seconds())
        # No explicit label -> unlabeled (never silently a success).
        label = cmd.label or "unlabeled"
        write_meta(
            self._ep_dir,
            build_metadata(
                route=self._cur_route,
                operator=self._cur_operator,
                index=self._index,
                started_at=self._started,
                stopped_at=stopped,
                label=label,
                notes=cmd.notes,
                topics=self._topics,
                bag_dir="bag",
                ros_domain_id=self._domain_id,
            ),
        )
        self.get_logger().info(f"✓ saved {self._ep_dir.name}  label={label}  ({dur})")
        self._index += 1
        self._reset_episode()

    def _discard(self) -> None:
        """Stop the bag and delete the episode directory (a thrown-away run)."""
        if self._proc is None or self._ep_dir is None:
            self.get_logger().warn("not recording; ignoring discard")
            return
        stop_bag(self._proc)
        name = self._ep_dir.name
        shutil.rmtree(self._ep_dir, ignore_errors=True)
        self.get_logger().info(f"✗ discarded {name}")
        self._reset_episode()

    def _reset_episode(self) -> None:
        """Return to the idle state (no bag open)."""
        self._proc = None
        self._ep_dir = None
        self._started = None

    def shutdown(self) -> None:
        """Finalise any in-flight episode as unlabeled so a run isn't lost."""
        if self._proc is None:
            return
        stop_bag(self._proc)
        if self._ep_dir is not None and self._started is not None:
            stopped = datetime.now()
            write_meta(
                self._ep_dir,
                build_metadata(
                    route=self._cur_route,
                    operator=self._cur_operator,
                    index=self._index,
                    started_at=self._started,
                    stopped_at=stopped,
                    label="unlabeled",
                    notes="interrupted (node shutdown)",
                    topics=self._topics,
                    bag_dir="bag",
                    ros_domain_id=self._domain_id,
                ),
            )
            self.get_logger().info(f"✓ finalised {self._ep_dir.name} label=unlabeled")
        self._reset_episode()


def main(args: list[str] | None = None) -> None:
    """Spin the recorder, finalising any in-flight episode on exit."""
    rclpy.init(args=args)
    node = EpisodeRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
