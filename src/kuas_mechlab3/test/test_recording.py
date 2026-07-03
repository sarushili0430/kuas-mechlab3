"""Unit tests for the pure episode-recording helpers (no ROS / IO deps)."""

from datetime import datetime

from kuas_mechlab3.recording import (
    ACTION_TOPIC,
    IMAGE_TOPICS,
    build_metadata,
    default_topics,
    episode_dirname,
    format_duration,
    normalize_label,
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
