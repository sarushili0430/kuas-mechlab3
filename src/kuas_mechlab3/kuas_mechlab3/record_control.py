"""Pure protocol for the recording-control HTTP API (no ROS / IO / subprocess).

Single owner of the wire contract the cockpit's REC button speaks: the small JSON
request bodies for start / stop and the JSON response payloads that report the
recording state. Keeping this as string<->dict functions lets the standalone
pytest job cover the parsing and the schema; ``record_server`` owns the HTTP
socket and the threading, and ``record_session`` owns the ``ros2 bag record``
subprocess on top of this module (the same split as ``teleop_command`` vs.
``teleop_server``).

The control surface is deliberately tiny -- start, stop, discard, status -- so a
phone can flag an imitation-learning episode's begin and end without touching the
Pi terminal. It carries no auth (LAN-only, like the teleop and MJPEG channels).
"""

import json
from dataclasses import dataclass
from typing import Any

from kuas_mechlab3.recording import normalize_label

# HTTP routes (path only; all mutating routes are POST, status is GET). The server
# matches inbound requests on these exact paths.
STATUS_PATH = "/record/status"
START_PATH = "/record/start"
STOP_PATH = "/record/stop"
DISCARD_PATH = "/record/discard"


@dataclass(frozen=True)
class StartOptions:
    """Per-episode overrides parsed from a start request.

    ``None`` means "field absent" so the server falls back to its configured
    default (route / operator / which topics to record) rather than a hardcoded
    value -- the phone may send only what it wants to override.
    """

    route: str | None = None
    operator: str | None = None
    include_rear: bool | None = None
    include_state: bool | None = None


@dataclass(frozen=True)
class StopOptions:
    """Label + notes parsed from a stop request (label already canonicalised).

    The label is run through ``recording.normalize_label`` here so a fat-fingered
    value can never reach the metadata as a silent ``success`` (see that helper);
    an absent label defaults to ``success``, matching the interactive recorder.
    """

    label: str
    notes: str


def _as_object(raw: str) -> dict[str, Any]:
    """Parse a JSON request body into a dict; anything else -> empty dict.

    A missing / malformed / non-object body is treated as "no fields given" so
    the server falls back to its configured defaults instead of erroring on an
    empty POST -- the common case of a start with no overrides.
    """
    try:
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _opt_str(data: dict[str, Any], key: str) -> str | None:
    """Return a non-blank stripped string for ``key``, else None."""
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _opt_bool(data: dict[str, Any], key: str) -> bool | None:
    """Return the bool at ``key`` if it is genuinely a bool, else None."""
    value = data.get(key)
    return value if isinstance(value, bool) else None


def parse_start_request(raw: str) -> StartOptions:
    """Parse a ``/record/start`` body ``{route?, operator?, rear?, state?}``.

    Every field is optional; absent / wrong-typed fields become None so the
    server supplies its default. Never raises -- a broken body yields all-None.
    """
    data = _as_object(raw)
    return StartOptions(
        route=_opt_str(data, "route"),
        operator=_opt_str(data, "operator"),
        include_rear=_opt_bool(data, "rear"),
        include_state=_opt_bool(data, "state"),
    )


def parse_stop_request(raw: str) -> StopOptions:
    """Parse a ``/record/stop`` body ``{label?, notes?}`` into canonical form."""
    data = _as_object(raw)
    raw_label = data.get("label")
    label = normalize_label(raw_label if isinstance(raw_label, str) else "")
    raw_notes = data.get("notes")
    notes = raw_notes.strip() if isinstance(raw_notes, str) else ""
    return StopOptions(label=label, notes=notes)


def status_payload(
    *,
    recording: bool,
    index: int,
    episode: str | None,
    started_at: str | None,
    route: str,
    operator: str,
) -> dict[str, Any]:
    """Shape the ``/record/status`` response (also the reply to a start)."""
    return {
        "recording": recording,
        "index": index,
        "episode": episode,
        "started_at": started_at,
        "route": route,
        "operator": operator,
    }


def stopped_payload(
    *,
    saved: str,
    index: int,
    label: str,
    notes: str,
    duration_s: float,
) -> dict[str, Any]:
    """Shape the reply to a successful stop (episode saved with a label)."""
    return {
        "recording": False,
        "saved": saved,
        "index": index,
        "label": label,
        "notes": notes,
        "duration_s": duration_s,
    }


def discarded_payload(*, episode: str, index: int) -> dict[str, Any]:
    """Shape the reply to a discard (episode dropped; the index is reused)."""
    return {"recording": False, "discarded": True, "episode": episode, "index": index}


def error_payload(reason: str) -> dict[str, Any]:
    """Shape an error body, e.g. ``already_recording`` / ``not_recording``."""
    return {"recording": None, "error": reason}
