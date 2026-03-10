"""Tests for Strava OAuth utilities."""
from datetime import datetime, timedelta, timezone

from fitops.strava.oauth import validate_strava_token


def test_valid_token():
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    assert validate_strava_token("some_token", expires_at) is True


def test_expired_token():
    expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    assert validate_strava_token("some_token", expires_at) is False


def test_token_within_buffer():
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)
    assert validate_strava_token("some_token", expires_at) is False


def test_no_token():
    assert validate_strava_token(None, None) is False


def test_no_expiry():
    assert validate_strava_token("token", None) is False
