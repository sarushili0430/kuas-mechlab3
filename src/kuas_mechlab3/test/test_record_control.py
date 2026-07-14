"""Unit tests for the pure recording-control protocol (no ROS / IO deps)."""

from kuas_mechlab3.record_control import (
    discarded_payload,
    error_payload,
    parse_start_request,
    parse_stop_request,
    status_payload,
    stopped_payload,
)

# -- parse_start_request ----------------------------------------------------


def test_parse_start_reads_overrides() -> None:
    opts = parse_start_request('{"route": "loop_1", "operator": "koyu", "rear": false}')
    assert opts.route == "loop_1"
    assert opts.operator == "koyu"
    assert opts.include_rear is False
    assert opts.include_state is None  # absent -> server default


def test_parse_start_empty_body_is_all_none() -> None:
    # a start with no overrides is the common case; every field falls back
    opts = parse_start_request("")
    assert opts.route is None
    assert opts.operator is None
    assert opts.include_rear is None
    assert opts.include_state is None


def test_parse_start_ignores_blank_and_wrong_types() -> None:
    opts = parse_start_request('{"route": "   ", "rear": "yes", "state": 1}')
    assert opts.route is None  # blank -> None
    assert opts.include_rear is None  # non-bool -> None
    assert opts.include_state is None  # 1 is not a bool -> None


def test_parse_start_broken_json_is_all_none() -> None:
    opts = parse_start_request("{not json")
    assert opts == parse_start_request("")


# -- parse_stop_request -----------------------------------------------------


def test_parse_stop_normalizes_label() -> None:
    assert parse_stop_request('{"label": "f"}').label == "failure"
    assert parse_stop_request('{"label": "success"}').label == "success"


def test_parse_stop_absent_label_defaults_success() -> None:
    # matches the interactive recorder: a blank label means success
    assert parse_stop_request("{}").label == "success"


def test_parse_stop_typo_is_not_silently_success() -> None:
    # a fat-fingered label must never poison the dataset as a success
    assert parse_stop_request('{"label": "sucess"}').label == "unlabeled"


def test_parse_stop_reads_notes() -> None:
    assert parse_stop_request('{"label": "success", "notes": "  clear  "}').notes == (
        "clear"
    )
    assert parse_stop_request('{"label": "success"}').notes == ""


# -- payload builders -------------------------------------------------------


def test_status_payload_shape() -> None:
    payload = status_payload(
        recording=True,
        index=3,
        episode="20260703-120000_route-a_003",
        started_at="2026-07-03T12:00:00",
        route="route_a",
        operator="koyu",
    )
    assert payload["recording"] is True
    assert payload["index"] == 3
    assert payload["episode"] == "20260703-120000_route-a_003"


def test_stopped_payload_shape() -> None:
    payload = stopped_payload(
        saved="ep_001", index=1, label="success", notes="", duration_s=34.0
    )
    assert payload["recording"] is False
    assert payload["saved"] == "ep_001"
    assert payload["label"] == "success"
    assert payload["duration_s"] == 34.0


def test_discarded_payload_reuses_index() -> None:
    payload = discarded_payload(episode="ep_002", index=2)
    assert payload["recording"] is False
    assert payload["discarded"] is True
    assert payload["index"] == 2  # index not advanced on discard


def test_error_payload_shape() -> None:
    payload = error_payload("already_recording")
    assert payload["recording"] is None
    assert payload["error"] == "already_recording"
