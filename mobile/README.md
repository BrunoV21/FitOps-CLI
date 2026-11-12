# FitOps Mobile

Independent Android fitness app in the FitOps repository. Initial scope: calibrated heart-rate zones, activity TSS, and running VO₂max estimates, with local storage and optional desktop export.

- [Architecture and implementation boundaries](architecture.md)
- [UI mockups](mockups/README.md) — open `mockups/index.html` in a browser.
- [Huawei approval and release plan](../docs/providers/huawei/mobile-appgallery-plan.md)
- [Design tokens](src/theme/tokens.json)
- [Android usage guide](../docs/official/mobile/index.md)
- [AppGallery release checklist](docs/appgallery-release.md)
- [Health Kit reapplication draft](docs/huawei-reapplication.md)
- [QA build and screenshot workflow](docs/qa-screenshots.md)
- [Build and verification record](docs/verification.md)
- [AppGallery listing and reviewer material pack](release/README.md)

The React Native application is implemented under `src/`, with an independent package manifest and lockfile. Native build and device verification are tracked separately from implementation; do not treat this README as evidence of AppGallery publication. Huawei access is not integrated or approved. No Huawei credentials are requested by the initial file-based app.

The app imports TCX and version-1 FitOps JSON activity files, stores records locally in SQLite, calculates cached metrics using sport-specific calibration, and exports selected records through Android sharing. Training sessions, form/readiness, native HarmonyOS, and live recording are deferred. Mockup values remain synthetic visual examples, not calculation reference fixtures.

## Development

```sh
cd mobile
npm ci
npm run validate
npm run android
```

`npm run android` builds/runs the native Android application using the installed Android SDK and a connected device or emulator. The first Huawei-enabled integration will also require a native build; Expo Go does not prove Huawei SDK support.

`npm run build:internal` creates a bundled, debug-signed **FitOps QA** APK under the separate `.internal` application ID. It preloads three labelled synthetic runs and sample calibration once in its own QA database for screenshot/testing use. The **QA library** menu can explicitly replace the QA library with those examples; erasing it stays erased until reload. Production builds disable QA mode and do not preload demo records. See the [QA workflow](docs/qa-screenshots.md).

Internal builds target `arm64-v8a` by default; set `FITOPS_ANDROID_ARCHITECTURES` for a different internal-test ABI. The latest preloaded QA build was installed on an RMX3851 running Android 16; native startup, demo preload, and navigation were checked, and three labelled native screenshots were captured. Native TCX import, repeat-import deduplication, the export chooser, demo reset, and process-restart persistence were also checked. A production-mode arm64 unsigned APK built successfully with QA mode disabled. Recipient-side export reading, further device coverage, owner signing, and public release remain pending. See the [verification record](docs/verification.md) for artifact paths, hashes, and the scope of completed checks.

For USB development when the phone cannot reach Metro over Wi-Fi:

```sh
adb devices
adb reverse tcp:8081 tcp:8081
npx expo start --localhost --android
```

An APK intended for AppGallery must have a JavaScript bundle included and use the owner-managed release signing identity. A development build that depends on Metro, or a release-mode build signed with a debug key, is not a store-ready artifact. Follow the [release checklist](docs/appgallery-release.md) before publishing.

Existing Python packaging remains separate. The reference project is `../BranchBalance` (the actual local directory corresponding to the requested `../branch-balance`). The app adapts its organization, theme-provider, composition, and UI primitive patterns; see [third-party notices](THIRD_PARTY_NOTICES.md).
