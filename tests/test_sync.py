"""Tests for sync engine utilities."""

from datetime import UTC, datetime, timedelta

from fitops.strava.sync_engine import OVERLAP_DAYS


def test_overlap_days_value():
    assert OVERLAP_DAYS == 3


def test_overlap_calculation():
    last_sync = datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)
    overlap_start = last_sync - timedelta(days=OVERLAP_DAYS)
    assert overlap_start == datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)
