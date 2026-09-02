from __future__ import annotations

from unittest.mock import AsyncMock, patch


def test_backup_page_renders_saved_ui_state(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    monkeypatch.setenv("FITOPS_DIR", str(tmp_path))

    with patch("fitops.db.migrations.create_all_tables", new_callable=AsyncMock):
        with patch(
            "fitops.dashboard.routes.backup.run_scheduler", new_callable=AsyncMock
        ):
            with patch(
                "fitops.dashboard.routes.auto_sync.run_auto_sync_scheduler",
                new_callable=AsyncMock,
            ):
                with patch(
                    "fitops.dashboard.routes.backup.bcfg.get_github_config",
                    return_value={"token": "secret", "repo": "owner/backups"},
                ):
                    with patch(
                        "fitops.dashboard.routes.backup.bcfg.get_schedule_config",
                        return_value={
                            "enabled": True,
                            "interval_hours": 12,
                            "provider": "github",
                        },
                    ):
                        from fitops.dashboard.server import create_app

                        with TestClient(create_app()) as client:
                            resp = client.get("/backup")

    assert resp.status_code == 200
    assert 'repo: "owner/backups"' in resp.text
    assert "interval_hours: 12" in resp.text
    assert 'id="webhook-enable-btn"' in resp.text
    assert 'id="sched-save-btn"' in resp.text
