import pytest

from kuas_mechlab3.utils import clamp


def test_clamp_within_range() -> None:
    assert clamp(5.0, 0.0, 10.0) == 5.0


def test_clamp_below_lower() -> None:
    assert clamp(-1.0, 0.0, 10.0) == 0.0


def test_clamp_above_upper() -> None:
    assert clamp(11.0, 0.0, 10.0) == 10.0


def test_clamp_invalid_range() -> None:
    with pytest.raises(ValueError):
        clamp(1.0, 10.0, 0.0)
