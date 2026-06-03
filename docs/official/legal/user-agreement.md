# User Agreement

Last updated: June 3, 2026

This agreement describes the terms for using FitOps, an open source, local-first fitness analytics tool.

By using FitOps, you agree to use it responsibly and to review how it handles your fitness and health data.

## What FitOps Provides

FitOps provides:

- a command-line interface for syncing and analyzing training data;
- a local web dashboard for visual exploration;
- local storage for synced activities and computed analytics;
- optional backup and deployment workflows that you control.

FitOps is not a medical device, healthcare provider, or emergency service. Analytics, estimates, and recommendations are informational only and are not medical advice.

## Your Responsibilities

You are responsible for:

- choosing which providers to connect;
- granting or revoking provider permissions;
- protecting your local machine and credentials;
- reviewing any optional deployment or backup destination before using it;
- complying with the terms of third-party providers you connect to FitOps;
- deciding how to use training analytics in your own training.

Do not rely on FitOps for medical diagnosis, treatment, injury prevention, emergency response, or any safety-critical decision.

## Provider Access

FitOps accesses third-party fitness data only after you authorize a provider connection. For planned Huawei Health Kit support, Health Kit data access will require Huawei approval and user authorization before FitOps can import Huawei data.

FitOps should request only the provider permissions needed for the feature you are using. You may revoke provider authorization through the provider's account or app settings.

## Local Data

FitOps stores imported data locally by default. Deleting provider authorization stops future syncs, but it does not automatically remove data already stored in your local FitOps database.

You control your local data directory, local database, optional backups, and optional deployed dashboard environment.

## Optional Deployment And Backup

If you deploy FitOps or configure backups, you are responsible for the hosting service, repository, storage location, passwords, tokens, secrets, and access controls. FitOps maintainers do not operate a FitOps cloud service for your account.

## Acceptable Use

You may not use FitOps to:

- access another person's fitness or health data without authorization;
- bypass provider permissions or user consent;
- publish private activity data without permission;
- misrepresent FitOps analytics as medical advice or clinical measurement.

## Changes

FitOps may update this agreement as the project evolves, especially when new provider integrations or deployment options are added.

## Contact

For questions about this agreement, open an issue in the project repository:

https://github.com/BrunoV21/FitOps-CLI/issues
