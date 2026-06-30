"""Unit tests for the pure episode-recording helpers (no ROS / IO deps)."""

from datetime import datetime

from kuas_mechlab3.recording import (
    ACTION_TOPIC,
    IMAGE_TOPICS,
    RECORD_ACTIONS,
    RecordCommand,
    build_metadata,
    default_topics,
    episode_dirname,
    format_duration,
    normalize_label,
    parse_record_command,
    record_command_to_json,
    slugify,
)

FIXED_START = datetime(2026, 6, 19, 12, 34, 56)
FIXED_STOP = datetime(2026, 6, 19, 12, 35, 30)  # +34 s


# -- slugify ----------------------------------------------------------------


def test_slugify_lowercases_and_replaces_spaces() -> None:
    assert slugify("Route A") == "route-a"


def test_slugify_collapses_runs_and_strips() -> None:
    assert slugify("  loop // 2  ") == "loop-2"


def test_slugify_empty_falls_back() -> None:
    assert slugify("!!!") == "x"


# -- episode_dirname --------------------------------------------------------


def test_episode_dirname_is_sortable_and_descriptive() -> None:
    assert episode_dirname(FIXED_START, "Route A", 1) == "20260619-123456_route-a_001"


# -- default_topics ---------------------------------------------------------


def test_default_topics_includes_action_and_both_cameras() -> None:
    topics = default_topics()
    assert topics[0] == ACTION_TOPIC  # action first
    assert IMAGE_TOPICS[0] in topics
    assert IMAGE_TOPICS[1] in topics


def test_default_topics_can_drop_rear_and_state() -> None:
    assert default_topics(include_rear=False, include_state=False) == [
        ACTION_TOPIC,
        IMAGE_TOPICS[0],
    ]


# -- normalize_label --------------------------------------------------------


def test_normalize_label_blank_is_success() -> None:
    assert normalize_label("") == "success"


def test_normalize_label_failure_keys() -> None:
    assert normalize_label("f") == "failure"
    assert normalize_label("2") == "failure"


def test_normalize_label_unknown_is_unlabeled() -> None:
    # a typo must NOT silently become a success that poisons the dataset
    assert normalize_label("xyz") == "unlabeled"


# -- build_metadata ---------------------------------------------------------


def test_build_metadata_core_fields() -> None:
    meta = build_metadata(
        route="Route A",
        operator="koyu",
        index=1,
        started_at=FIXED_START,
        stopped_at=FIXED_STOP,
        label="success",
        notes="clear weather",
        topics=default_topics(),
        bag_dir="bag",
        ros_domain_id=11,
    )
    assert meta["duration_s"] == 34.0
    assert meta["action_topic"] == ACTION_TOPIC
    assert meta["image_topics"] == list(IMAGE_TOPICS)
    assert meta["label"] == "success"
    assert meta["ros_domain_id"] == 11
    assert meta["schema_version"] >= 1


def test_build_metadata_rejects_bogus_label() -> None:
    meta = build_metadata(
        route="r",
        operator="o",
        index=2,
        started_at=FIXED_START,
        stopped_at=FIXED_STOP,
        label="totally-bogus",
        notes="",
        topics=default_topics(),
        bag_dir="bag",
    )
    assert meta["label"] == "unlabeled"


# -- format_duration --------------------------------------------------------


def test_format_duration_minutes_seconds() -> None:
    assert format_duration(34) == "0:34"
    assert format_duration(95) == "1:35"


# -- parse_record_command ---------------------------------------------------


def test_parse_record_command_start_minimal() -> None:
    assert parse_record_command('{"record": "start"}') == RecordCommand(action="start")


def test_parse_record_command_start_with_overrides() -> None:
    cmd = parse_record_command(
        '{"record": "start", "route": "Loop 2", "operator": "koyu"}'
    )
    assert cmd == RecordCommand(action="start", route="Loop 2", operator="koyu")


def test_parse_record_command_stop_with_label_and_notes() -> None:
    cmd = parse_record_command(
        '{"record": "stop", "label": "f", "notes": "  drifted "}'
    )
    # label is normalised (f -> failure) and notes trimmed
    assert cmd == RecordCommand(action="stop", label="failure", notes="drifted")


def test_parse_record_command_stop_without_label_leaves_none() -> None:
    # absent label stays None so the recorder applies its own default (not success)
    assert parse_record_command('{"record": "stop"}') == RecordCommand(action="stop")


def test_parse_record_command_action_is_case_insensitive() -> None:
    assert parse_record_command('{"record": "STOP"}') == RecordCommand(action="stop")


def test_parse_record_command_all_actions_supported() -> None:
    for action in RECORD_ACTIONS:
        parsed = parse_record_command(f'{{"record": "{action}"}}')
        assert parsed is not None and parsed.action == action


def test_parse_record_command_unknown_action_returns_none() -> None:
    assert parse_record_command('{"record": "pause"}') is None


def test_parse_record_command_drive_message_returns_none() -> None:
    # a {"vx","wz"} drive command has no record key -> not a record command
    assert parse_record_command('{"vx": 0.5, "wz": -0.3}') is None


def test_parse_record_command_ignores_extra_keys() -> None:
    cmd = parse_record_command('{"record": "start", "seq": 7}')
    assert cmd == RecordCommand(action="start")


def test_parse_record_command_blank_overrides_become_none() -> None:
    cmd = parse_record_command('{"record": "start", "route": "   ", "operator": ""}')
    assert cmd == RecordCommand(action="start", route=None, operator=None)


def test_parse_record_command_bad_json_returns_none() -> None:
    assert parse_record_command("{not json") is None
    assert parse_record_command("") is None


def test_parse_record_command_non_object_returns_none() -> None:
    assert parse_record_command('"start"') is None
    assert parse_record_command("[1, 2]") is None


def test_parse_record_command_non_string_action_returns_none() -> None:
    assert parse_record_command('{"record": 1}') is None


# -- record_command_to_json (round-trip) ------------------------------------


def test_record_command_to_json_omits_unset_fields() -> None:
    assert (
        record_command_to_json(RecordCommand(action="start")) == '{"record": "start"}'
    )


def test_record_command_to_json_round_trips_full_command() -> None:
    cmd = RecordCommand(
        action="stop", route="route-a", operator="koyu", label="success", notes="clear"
    )
    assert parse_record_command(record_command_to_json(cmd)) == cmd


def test_record_command_to_json_round_trips_start_overrides() -> None:
    cmd = RecordCommand(action="start", route="loop-2", operator="rin")
    assert parse_record_command(record_command_to_json(cmd)) == cmd
