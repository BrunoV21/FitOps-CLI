"""Tests for sync engine utilities."""

from datetime import UTC, datetime, timedelta

from fitops.strava.sync_engine import OVERLAP_DAYS


def test_overlap_days_value():
    assert OVERLAP_DAYS == 3


def test_overlap_calculation():
    last_sync = datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)
    overlap_start = last_sync - timedelta(days=OVERLAP_DAYS)
    assert overlap_start == datetime(2026, 3, 7, 12, 0, 0, tzinfo=UTC)


def test_sync_state_data_update_stamp_is_independent(tmp_path, monkeypatch):
    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))

    import fitops.config.settings as settings_module

    settings_module._settings = None

    from fitops.config.state import get_sync_state

    state = get_sync_state()
    state.mark_data_updated("webhook_create", {"object_id": 123})
    data_update_at = state.last_data_update_at

    assert data_update_at is not None
    assert state.last_sync_at is None

    state.update_after_sync(
        sync_type="webhook_create",
        activities_created=1,
        activities_updated=0,
        duration_s=0.0,
        mark_data_update=False,
    )

    refreshed = get_sync_state()
    assert refreshed.last_sync_at is not None
    assert refreshed.last_data_update_at == data_update_at
