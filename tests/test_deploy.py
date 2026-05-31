from __future__ import annotations

import inspect
import time


def test_hf_space_secrets_enable_default_webhook():
    from fitops.cli.deploy import _build_hf_space_secrets

    secrets = _build_hf_space_secrets(
        pw_hash="hash",
        totp_secret="totp",
        session_secret="session",
        sync_token="sync",
        public_base_url="https://user-fitops-dashboard.hf.space",
        webhook_url="https://user-fitops-dashboard.hf.space/api/strava/webhook",
        github_backup_token="gh-token",
        github_backup_repo="user/backups",
        strava_client_id="175267",
        strava_client_secret="strava-secret",
    )

    assert secrets["FITOPS_AUTH_ENABLED"] == "true"
    assert (
        secrets["FITOPS_WEBHOOK_CALLBACK_URL"]
        == "https://user-fitops-dashboard.hf.space/api/strava/webhook"
    )
    assert secrets["FITOPS_DEFAULT_SYNC_MODE"] == "webhook"
    assert secrets["FITOPS_INSTANCE_KIND"] == "hf-space"
    assert secrets["FITOPS_INSTANCE_ROLE"] == "primary"
    assert secrets["FITOPS_INSTANCE_LABEL"] == "user-fitops-dashboard.hf.space"
    assert secrets["FITOPS_PUBLIC_BASE_URL"] == "https://user-fitops-dashboard.hf.space"
    assert secrets["FITOPS_STRAVA_CLIENT_ID"] == "175267"
    assert secrets["FITOPS_STRAVA_CLIENT_SECRET"] == "strava-secret"


def test_hf_webhook_setup_message_uses_derived_url_and_domain():
    from fitops.cli.deploy import _format_webhook_setup_message

    message = _format_webhook_setup_message(
        "user",
        "fitops-dashboard",
        "https://user-fitops-dashboard.hf.space/api/strava/webhook",
    )

    assert (
        "Configured webhook URL: "
        "https://user-fitops-dashboard.hf.space/api/strava/webhook"
    ) in message
    assert "FITOPS_WEBHOOK_CALLBACK_URL" in message
    assert "Authorization Callback Domain" in message
    assert "user-fitops-dashboard.hf.space" in message
    assert "Do not paste the full webhook URL" in message


def test_hf_github_actions_is_keepalive_only():
    from fitops.cli.deploy import _build_gha_yaml

    workflow = _build_gha_yaml("https://user-fitops-dashboard.hf.space")

    assert "name: FitOps Keepalive" in workflow
    assert "curl -sf https://user-fitops-dashboard.hf.space/health" in workflow
    assert "release:" not in workflow
    assert "/api/internal/sync" not in workflow


def test_hf_startup_restores_only_matching_hf_origin_backup():
    from pathlib import Path

    startup = Path("fitops/cloud/hf_space/startup.sh").read_text()

    assert "fitops backup restore" in startup
    assert "--origin-kind hf-space" in startup
    assert "--origin-role primary" in startup
    assert "--origin-label \"$FITOPS_INSTANCE_LABEL\"" in startup
    assert "No HF-origin backup found" in startup
    assert "FITOPS_STRAVA_CLIENT_ID" in startup
    assert "settings.save_credentials" in startup


def test_cli_deploy_does_not_call_hosted_api():
    import fitops.cli.deploy as deploy_cli

    source = inspect.getsource(deploy_cli)

    assert "deploy_api" not in source
    assert "api/deploy/hf/jobs" not in source


def test_hf_repo_validation_rejects_urls_and_paths():
    from fitops.cloud.deploy_hf import validate_repo_id

    validate_repo_id("user/fitops-dashboard")

    for value in [
        "https://huggingface.co/spaces/user/fitops",
        "user/../fitops",
        "/user/fitops",
        "user/fitops space",
        "user",
    ]:
        try:
            validate_repo_id(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected invalid repo: {value}")


def test_deploy_api_rejects_missing_or_disallowed_origin():
    from starlette.testclient import TestClient

    from fitops.cloud.deploy_api import create_app

    client = TestClient(create_app(allowed_origins=["https://docs.example"]))

    response = client.post("/api/deploy/hf/jobs", json={})
    assert response.status_code == 403

    response = client.post(
        "/api/deploy/hf/jobs",
        headers={"Origin": "https://evil.example"},
        json={},
    )
    assert response.status_code == 403


def test_deploy_api_rate_limits_job_creation(monkeypatch):
    from starlette.testclient import TestClient

    from fitops.cloud.deploy_api import DeployJobManager, RateLimiter, create_app

    async def fake_run_job(job_id: str) -> None:
        job = manager.jobs[job_id]
        job.status = "succeeded"
        job.result = {"app_url": "https://user-fitops.hf.space/"}
        job.clear_secrets()

    manager = DeployJobManager(max_concurrent_jobs=10)
    monkeypatch.setattr(manager, "run_job", fake_run_job)
    app = create_app(
        allowed_origins=["https://docs.example"],
        manager=manager,
        rate_limiter=RateLimiter(limit=1),
    )

    payload = {
        "hf_token": "hf_abcdefghijk",
        "hf_repo": "user/fitops-dashboard",
        "github_token": "ghp_abcdefghijk",
        "github_repo": "user/fitops-backups",
        "dashboard_password": "correct horse battery staple",
    }
    headers = {"Origin": "https://docs.example"}

    with TestClient(app) as client:
        assert (
            client.post("/api/deploy/hf/jobs", headers=headers, json=payload).status_code
            == 200
        )
        assert (
            client.post("/api/deploy/hf/jobs", headers=headers, json=payload).status_code
            == 429
        )


def test_deploy_api_stream_redacts_secrets(monkeypatch):
    from starlette.testclient import TestClient

    import fitops.cloud.deploy_api as deploy_api
    from fitops.cloud.deploy_hf import HfDeployResult

    def fake_deploy(request, *, progress=None):
        if progress:
            progress(
                f"Using {request.hf_token}, {request.github_backup_token}, "
                f"{request.strava_client_secret}"
            )
        assert request.strava_client_id == "175267"
        assert request.strava_client_secret == "strava-secret-value"
        return HfDeployResult(
            hf_repo="user/fitops-dashboard",
            space_url="https://huggingface.co/spaces/user/fitops-dashboard",
            app_url="https://user-fitops-dashboard.hf.space",
            webhook_url="https://user-fitops-dashboard.hf.space/api/strava/webhook",
            callback_domain="user-fitops-dashboard.hf.space",
        )

    monkeypatch.setattr(deploy_api, "deploy_hf_space", fake_deploy)
    app = deploy_api.create_app(
        allowed_origins=["https://docs.example"],
        manager=deploy_api.DeployJobManager(timeout_seconds=5),
        rate_limiter=deploy_api.RateLimiter(limit=10),
    )
    payload = {
        "hf_token": "hf_abcdefghijklmnop",
        "hf_repo": "user/fitops-dashboard",
        "github_token": "ghp_abcdefghijklmnop",
        "github_repo": "user/fitops-backups",
        "dashboard_password": "correct horse battery staple",
        "strava_client_id": "175267",
        "strava_client_secret": "strava-secret-value",
    }
    headers = {"Origin": "https://docs.example"}

    with TestClient(app) as client:
        created = client.post("/api/deploy/hf/jobs", headers=headers, json=payload)
        assert created.status_code == 200
        job_id = created.json()["job_id"]

        deadline = time.time() + 3
        status = {}
        while time.time() < deadline:
            status = client.get(
                f"/api/deploy/hf/jobs/{job_id}", headers=headers
            ).json()
            if status["status"] == "succeeded":
                break
            time.sleep(0.05)

        assert status["status"] == "succeeded"
        serialized_status = str(status)
        assert "hf_abcdefghijklmnop" not in serialized_status
        assert "ghp_abcdefghijklmnop" not in serialized_status
        assert status["result"]["app_url"] == "https://user-fitops-dashboard.hf.space/"

        with client.stream(
            "GET", f"/api/deploy/hf/jobs/{job_id}/events", headers=headers
        ) as response:
            body = response.read().decode()

        assert response.status_code == 200
    assert "hf_abcdefghijklmnop" not in body
    assert "ghp_abcdefghijklmnop" not in body
    assert "strava-secret-value" not in body
    assert "[REDACTED]" in body
