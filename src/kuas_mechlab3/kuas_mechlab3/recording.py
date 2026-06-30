"""Pure helpers for episode recording (no ROS / filesystem / subprocess deps).

Single owner of the on-disk dataset layout and metadata schema for human teleop
demonstrations: which topics make up an episode, how episode directories are
named, and the metadata sidecar that lets an offline converter (-> LeRobot, etc.)
find the action stream, the camera streams, and the success/failure label. The
operational script ``scripts/record_episodes.py`` owns the subprocess (ros2 bag),
signal handling, and stdin; this module stays import-clean so the standalone
pytest job can cover the naming and schema without a sourced ROS2 environment
(same split as ``utils`` / ``teleop_command`` vs. the nodes).

It also owns the *remote record-control protocol* (``parse_record_command`` /
``record_command_to_json`` / ``RECORD_TOPIC``): the small JSON message the
operator sends over the teleop WebSocket to start / stop / discard an episode.
``teleop_server`` parses it (so the operator can drive recording from the same
cockpit they steer from) and relays it on ``RECORD_TOPIC``; the ``episode_recorder``
node consumes it and owns the bag lifecycle. Keeping the parse/serialise here --
pure and pytest-covered -- mirrors ``teleop_command`` owning the drive-command
wire format while ``teleop_server`` owns only the socket and the ROS publishing.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1

# The normalised command published by teleop_server: THE action label, already in
# the policy's own output space (vx, wz in [-1, 1]). See teleop_command.command_to_norm.
ACTION_TOPIC = "/cmd_norm"

# Camera observations (JPEG CompressedImage), front first.
IMAGE_TOPICS = (
    "/front_camera/image_raw/compressed",
    "/rear_camera/image_raw/compressed",
)

# Cheap state proxies: /cmd_vel is the physical twin of the action; wheel_pwm is the
# applied drive; wheel_rpm is constant 0 on this open-loop kit but kept for the day
# encoders land. Recorded for debugging / replay, not required for training.
STATE_TOPICS = (
    "/cmd_vel",
    "/mbed_driver/wheel_pwm",
    "/mbed_driver/wheel_rpm",
)

VALID_LABELS = ("success", "failure", "unlabeled")

# Relay topic for remote record control: teleop_server publishes the operator's
# start/stop/discard command here (std_msgs/String, JSON payload) and the
# episode_recorder node subscribes. Absolute so publisher and subscriber match
# regardless of node namespace (same convention as ACTION_TOPIC above).
RECORD_TOPIC = "/record_cmd"

# The three things an operator can ask the recorder to do, mid-demo, from teleop.
RECORD_ACTIONS = ("start", "stop", "discard")


def slugify(text: str) -> str:
    """Reduce a free-text route / operator name to a filesystem-safe slug.

    Lowercases, turns any run of non-alphanumerics into a single dash, trims
    leading/trailing dashes, and never returns empty (falls back to ``x``).
    """
    lowered = [c.lower() if c.isalnum() else "-" for c in text.strip()]
    slug = "".join(lowered)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "x"


def episode_dirname(started_at: datetime, route: str, index: int) -> str:
    """Build a sortable, descriptive episode directory name.

    ``20260619-123456_route-a_001`` -- timestamp first so a plain lexical sort is
    chronological, route slug for at-a-glance grouping, zero-padded index.
    """
    stamp = started_at.strftime("%Y%m%d-%H%M%S")
    return f"{stamp}_{slugify(route)}_{index:03d}"


def default_topics(include_rear: bool = True, include_state: bool = True) -> list[str]:
    """Assemble the default record set: action + image(s) + optional state.

    Action and front camera are always present (the minimum a vision->action
    policy needs); rear camera and state proxies are opt-out.
    """
    topics = [ACTION_TOPIC, IMAGE_TOPICS[0]]
    if include_rear:
        topics.append(IMAGE_TOPICS[1])
    if include_state:
        topics.extend(STATE_TOPICS)
    return topics


def normalize_label(raw: str) -> str:
    """Map a terse operator keystroke to a canonical label.

    Blank / y / s / 1 / success -> ``success``; n / f / 2 / fail -> ``failure``;
    anything else -> ``unlabeled`` so a fat-fingered entry never silently becomes a
    ``success`` that quietly poisons the training set.
    """
    key = raw.strip().lower()
    if key in ("", "y", "s", "1", "success", "ok"):
        return "success"
    if key in ("n", "f", "2", "fail", "failure", "bad"):
        return "failure"
    return "unlabeled"


def build_metadata(
    *,
    route: str,
    operator: str,
    index: int,
    started_at: datetime,
    stopped_at: datetime,
    label: str,
    notes: str,
    topics: list[str],
    bag_dir: str,
    ros_domain_id: int | None = None,
) -> dict[str, Any]:
    """Assemble the episode metadata sidecar (serialised to meta.json).

    Records which topic is the action vs. the images so a downstream converter
    needs no out-of-band knowledge, plus the label / notes for dataset filtering.
    An out-of-range label is coerced to ``unlabeled`` (never silently to success).
    """
    duration = max(0.0, (stopped_at - started_at).total_seconds())
    images = [t for t in topics if t in IMAGE_TOPICS]
    return {
        "schema_version": SCHEMA_VERSION,
        "route": route,
        "operator": operator,
        "episode_index": index,
        "started_at": started_at.isoformat(timespec="seconds"),
        "stopped_at": stopped_at.isoformat(timespec="seconds"),
        "duration_s": round(duration, 2),
        "label": label if label in VALID_LABELS else "unlabeled",
        "notes": notes,
        "action_topic": ACTION_TOPIC,
        "image_topics": images,
        "recorded_topics": list(topics),
        "bag_dir": bag_dir,
        "ros_domain_id": ros_domain_id,
    }


def format_duration(seconds: float) -> str:
    """Render seconds as ``M:SS`` for terse operator feedback."""
    whole = max(0, int(seconds))
    return f"{whole // 60}:{whole % 60:02d}"


@dataclass(frozen=True)
class RecordCommand:
    """A normalised remote record-control command (one start / stop / discard).

    ``action`` is one of ``RECORD_ACTIONS``. The rest are optional per-episode
    overrides carried on the wire so the operator can label and tag a run without
    a terminal on the Pi: ``route`` / ``operator`` refine a ``start``; ``label``
    (already mapped to success/failure/unlabeled) and ``notes`` annotate a
    ``stop``. ``None`` means "not supplied" -- the recorder fills its own default.
    """

    action: str
    route: str | None = None
    operator: str | None = None
    label: str | None = None
    notes: str = ""


def _clean_optional_str(value: Any) -> str | None:
    """Return a trimmed non-empty string, or None for anything else / blank."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def parse_record_command(raw: str) -> RecordCommand | None:
    """Parse one record-control message into a normalised ``RecordCommand``.

    Accepts ``{"record": "start"|"stop"|"discard", ...}`` (case-insensitive
    action) with optional ``route`` / ``operator`` (start) and ``label`` /
    ``notes`` (stop). ``label`` is mapped through ``normalize_label`` so a typo
    never silently becomes a success; an absent label stays ``None`` so the
    recorder can apply its own default. Returns ``None`` for anything that is not
    a well-formed record command -- bad JSON, a non-object, a missing/unknown
    ``record`` action -- so a caller multiplexing one socket can fall through to
    the drive-command parser (a ``{"vx","wz"}`` message has no ``record`` key and
    so returns ``None`` here; mirrors ``parse_command`` returning ``None`` for a
    record message).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    action_raw = data.get("record")
    if not isinstance(action_raw, str):
        return None
    action = action_raw.strip().lower()
    if action not in RECORD_ACTIONS:
        return None
    label_raw = data.get("label")
    label = normalize_label(label_raw) if isinstance(label_raw, str) else None
    return RecordCommand(
        action=action,
        route=_clean_optional_str(data.get("route")),
        operator=_clean_optional_str(data.get("operator")),
        label=label,
        notes=_clean_optional_str(data.get("notes")) or "",
    )


def record_command_to_json(cmd: RecordCommand) -> str:
    """Serialise a ``RecordCommand`` to the canonical relay JSON.

    Drops fields left unset so the payload stays minimal, and round-trips through
    ``parse_record_command`` unchanged. ``teleop_server`` relays this normalised
    form on ``RECORD_TOPIC`` (rather than the operator's raw bytes) so the
    recorder always receives a validated, already-normalised command.
    """
    payload: dict[str, str] = {"record": cmd.action}
    if cmd.route is not None:
        payload["route"] = cmd.route
    if cmd.operator is not None:
        payload["operator"] = cmd.operator
    if cmd.label is not None:
        payload["label"] = cmd.label
    if cmd.notes:
        payload["notes"] = cmd.notes
    return json.dumps(payload, ensure_ascii=False)
