# Huawei Health Kit Access

FitOps plans to support Huawei Health as a native data provider. Health Kit access must be approved in the Huawei Developer Console before an app can request Huawei health and fitness data from users.

Huawei describes Health Kit as an API surface that lets apps read or write health and fitness data after user authorization. Huawei's setup flow requires developers to apply for Health Kit, agree to the service agreement, select the requested data access permissions, and submit supporting application material.

Official Huawei references:

- [HUAWEI Health Kit](https://developer.huawei.com/consumer/en/hms/huaweihealth/)
- [Applying for Health Kit](https://developer.huawei.com/consumer/en/doc/development/HMSCore-Guides/apply-kitservice-0000001050071707)

## Application Fields

Use these FitOps documentation links when Huawei asks for public app policy material.

| Huawei form field | FitOps value |
|---|---|
| Link to the privacy policy disclosed by the app to users | `https://brunov21.github.io/FitOps-CLI/legal/privacy` |
| Agreement link | `https://brunov21.github.io/FitOps-CLI/legal/user-agreement` |
| App website | `https://github.com/BrunoV21/FitOps-CLI` |
| App documentation | `https://brunov21.github.io/FitOps-CLI/` |
| FitOps app icon | `https://brunov21.github.io/FitOps-CLI/assets/fitops-icon-216.png` |

## Required Review Material

Huawei's application screen asks for a document list uploaded as Excel or PDF. Use Huawei's current Excel or PDF template from the console, then fill every required sheet completely.

For FitOps, the material should explain:

- FitOps is a local-first fitness analytics tool.
- Health and fitness data is imported into the user's local SQLite database.
- The CLI and local dashboard read the same local dataset.
- FitOps does not sell user data.
- FitOps does not use user health data for advertising.
- FitOps does not train AI models on user data.
- Optional deployed dashboards are private and password protected.
- Users can revoke provider access and delete local data.

## Data Scopes

Apply for the smallest set of Health Kit permissions needed for the current integration.

For the first Huawei provider implementation, request only activity import scopes needed to sync workouts into FitOps. Do not request advanced health data such as sleep, stress, SpO2, ECG, or blood pressure until those features are implemented in both the CLI and dashboard.

If a future FitOps release adds Huawei sleep or stress analytics, update this page, the privacy policy, the user agreement, CLI docs, dashboard docs, and tests before requesting broader Huawei scopes.

## Authorization Entry Logo

If the Huawei form asks whether to display the Health Service Kit logo on the authorization entry, select the option that matches the app implementation submitted for review.

Use Huawei's official Health Service Kit logo artwork for Huawei authorization UI. Use the [FitOps icon](../assets/fitops-icon-216.png) only as the FitOps application icon.

## Purchase Plan

FitOps does not require Huawei ecosystem hardware purchases for users. If review or testing requires Huawei hardware, list only the devices that will actually be purchased or used for validation, including model name and quantity.

## User-Facing Consent

Health Kit data access must be shown to users before data is imported. The authorization flow should make clear:

- which Huawei data categories FitOps requests;
- that data is stored locally by default;
- that imported data is used for fitness analytics and dashboard display;
- that revoking Huawei authorization stops future Huawei sync;
- that deleting the local FitOps database removes imported local copies.

← [Authentication](./authentication.md) | [Next: First Sync →](./first-sync.md)
