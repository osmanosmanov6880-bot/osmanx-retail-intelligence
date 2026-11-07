"""Analytics invariants for empty stores and honest no-data state."""
from __future__ import annotations

from backend.analytics import _delta, REASONS


def test_delta_zero_denominator_is_unknown():
    assert _delta(20,0) is None
    assert _delta(0,10)==-100
    assert _delta(110,100)==10


def test_reasons_are_human_readable():
    assert 'size' in REASONS
    assert 'price' in REASONS
