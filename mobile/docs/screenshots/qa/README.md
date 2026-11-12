# Native QA screenshots

Captured on 2026-11-12 from the bundled FitOps QA Android application on an RMX3851 running Android 16. These are actual native screens with deterministic synthetic activities, not HTML mockups or live Huawei data. The visible **QA · DEMO DATA** label must remain.

- `01-overview-dark.png`: running estimate and recent activity stress.
- `02-activities-dark.png`: preloaded activity library.
- `03-zones-dark.png`: calibrated zone boundaries for the synthetic profile.

Each PNG is 1080 × 2376 and below 2 MB. The status bar was put temporarily in Android screenshot/demo mode; its original setting was restored after capture. No personal activities or notification contents are included.

Build: package `app.fitops.mobile.internal`, version `0.1.0-internal`, launcher name `FitOps QA`, arm64-v8a. APK SHA-256: `70fe2bb5b183231f7a64942017de23008e4809cec9477593ebd4ff537e699780`. The implementation is a working-tree build based on commit `73518e2`; this is not a production-signed AppGallery release.

The screenshots illustrate the planned public app functionality. They do not establish Huawei approval, live Huawei sync, or public AppGallery release evidence. Review the [QA screenshot workflow](../../qa-screenshots.md) and [release checklist](../../appgallery-release.md) before submission.
