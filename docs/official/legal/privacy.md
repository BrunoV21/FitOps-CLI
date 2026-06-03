# Privacy Policy

Last updated: June 3, 2026

FitOps is a local-first fitness analytics tool. It imports your activity data into a local SQLite database so you can analyze it through the FitOps CLI and dashboard.

This policy explains what FitOps does with your data when you use the local app, optional provider integrations, optional backup features, and optional deployed dashboard features.

## Data FitOps Processes

Depending on which features you enable, FitOps may process:

- fitness activities, workouts, routes, splits, laps, and streams;
- heart rate, cadence, power, pace, distance, elevation, and timing data;
- athlete profile details returned by a connected provider;
- provider account identifiers needed to sync your activities;
- OAuth tokens or other credentials needed to connect a provider;
- notes, planned workouts, race plans, and analysis results you create in FitOps;
- weather data used to calculate weather-adjusted pace.

For planned Huawei Health Kit support, FitOps will request only the Huawei data categories needed by the implemented feature. Broader health categories such as sleep, stress, SpO2, ECG, or blood pressure will not be requested unless the corresponding FitOps feature exists and the documentation is updated.

## How Data Is Used

FitOps uses your data to:

- sync fitness data from providers you authorize;
- store the synced data in your local FitOps database;
- calculate training analytics such as training load, zones, VO2max estimates, weather-adjusted pace, race simulation, and workout compliance;
- display those analytics in the local dashboard;
- return structured CLI output for your own scripts or AI agents.

FitOps does not sell your personal data. FitOps does not use your health or fitness data for advertising. FitOps does not train AI models on your data.

## Local Storage

By default, FitOps stores data on your machine under `~/.fitops/`, including the local SQLite database and configuration files.

No FitOps cloud account is required. The local CLI and local dashboard read from the same local database.

## Optional Deployed Dashboard

If you deploy the FitOps dashboard to a private hosting environment, such as a private HuggingFace Space, your FitOps data may be restored into that environment so the dashboard can run remotely.

The deployed dashboard is intended to be private and protected by authentication. You are responsible for the hosting account, secrets, access controls, and any backup repository you configure.

## Optional Backups

If you configure backups, FitOps may write database backups to the storage provider or repository you choose. Backup behavior is controlled by you. Review the privacy and security settings of any external backup destination before enabling it.

## Third-Party Providers

FitOps can connect to third-party fitness providers only when you authorize the connection. Provider authorization may involve OAuth or a similar user-consent flow.

Provider data is subject to that provider's own terms and privacy policy before it reaches FitOps. Revoking provider access stops future syncs from that provider, but it does not automatically delete data already imported into your local FitOps database.

## User Control

You can:

- stop using FitOps at any time;
- revoke provider access in the provider's account settings;
- remove saved FitOps credentials;
- delete local FitOps data by deleting the local FitOps data directory;
- remove optional backups from the backup destination you configured.

## Data Sharing

FitOps does not share your local data with FitOps maintainers. If you paste command output, screenshots, logs, database files, or backup files into an issue, chat, or support request, you are choosing to share that information in that separate context.

## Security

FitOps is designed for local use and stores sensitive data on your machine. Keep your operating system account, provider credentials, OAuth tokens, deployed dashboard password, TOTP seed, and backup tokens private.

## Contact

For privacy questions about FitOps, open an issue in the project repository:

https://github.com/BrunoV21/FitOps-CLI/issues
