from __future__ import annotations


def test_hf_space_secrets_enable_default_webhook():
    from fitops.cli.deploy import _build_hf_space_secrets

    secrets = _build_hf_space_secrets(
        pw_hash="hash",
        totp_secret="totp",
        session_secret="session",
        sync_token="sync",
        webhook_url="https://user-fitops-dashboard.hf.space/api/strava/webhook",
        github_backup_token="gh-token",
        github_backup_repo="user/backups",
    )

    assert secrets["FITOPS_AUTH_ENABLED"] == "true"
    assert (
        secrets["FITOPS_WEBHOOK_CALLBACK_URL"]
        == "https://user-fitops-dashboard.hf.space/api/strava/webhook"
    )
    assert secrets["FITOPS_DEFAULT_SYNC_MODE"] == "webhook"


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
