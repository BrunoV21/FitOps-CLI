# Android release and AppGallery checklist

Status: preparation checklist for the first independently useful, file-based Android app. Items below are not checked merely because code or a build script exists. Huawei sync is not available in this release.

The [concrete reviewer material pack](../release/README.md) contains English listing copy, production-app reviewer steps, a supported synthetic TCX download, expected results, and links to the native captures and local unsigned candidate.

## 1. Confirm application identity

- [ ] Verify the Huawei Developer account's identity, account type, and actual target countries/regions.
- [ ] Open app ID `117915041` in AppGallery Connect and verify its platform and registered package name.
- [ ] Confirm whether the Android app can use that existing registration. The code currently uses provisional package `app.fitops.mobile`; change it before distribution if the registered identity differs.
- [ ] Confirm app name, version, support contact, and package name across the APK, listing, policy, and Health Kit application.
- [ ] Keep native HarmonyOS out of the advertised supported platforms for this Android-only release.

AppGallery accepts Android APKs; HarmonyOS APP packages are a different release route. A second native HarmonyOS app is not part of this MVP. See Huawei's [release-format overview](https://developer.huawei.com/consumer/en/doc/app/agc-help-release-overview-0000001272395372/).

## 2. Verify the application before packaging

From `mobile/`:

```sh
npm ci
npm run validate
```

Record the exact commit, dependency lockfile, test output, device model, Android version, and build used for review. Tests and screenshots must come from the current app, not only the HTML mockups.

- [ ] Import a real supported TCX file with timestamped HR and distance/speed, review it, and save it locally.
- [ ] Repeat the import and verify that matching records update without duplicates.
- [ ] Import version-1 FitOps JSON and reject malformed/unsupported files gracefully.
- [ ] Save valid running/cycling/walking calibration and reject invalid/missing method inputs.
- [ ] Verify zone boundaries and measured time in zones, including sample gaps.
- [ ] Verify HR/pace stress estimates show their actual methods and unavailable states.
- [ ] Verify qualifying running VO₂max history and non-qualifying/missing-data states. Do not present an inferred value as a laboratory measurement or a validated confidence probability.
- [ ] Change calibration and verify retrospective recalculation of the same sport's saved activities.
- [ ] Close/reopen the app and verify persistence; repeat key read operations without network access.
- [ ] Select records, review the export warning, share a FitOps JSON file, and verify its contents at the chosen destination.
- [ ] Delete an activity, remove calibration, and erase the local library; confirm the scope of each operation.
- [ ] Verify System/Light/Dark themes, readable large text, small screens, screen-reader labels, Android back behavior, keyboard handling, and the navigation menu.
- [ ] Inspect the packaged permissions and backup settings; they must match actual behavior and policy disclosures.
- [ ] Confirm the app does not advertise working Huawei sync, request Huawei credentials, or ask for unapproved health permissions.

## 3. Keep internal testing and store signing distinct

The build workflow separates a bundled internal APK from a production release:

| Build | Purpose | Expected artifact |
|---|---|---|
| `npm run android` | Native development with Metro | Installed development build; not publication evidence |
| `npm run build:internal` | FitOps QA with bundled JavaScript, labelled synthetic preload, and debug signing | `android/app/build/outputs/apk/internal/app-internal.apk` |
| `npm run build:android` without release credentials | Release packaging without a production signature | `android/app/build/outputs/apk/release/app-release-unsigned.apk` |
| `npm run build:android` with valid owner-managed signing credentials | Candidate production APK, subject to verification | `android/app/build/outputs/apk/release/app-release.apk` |

The internal build uses a `.internal` package suffix and `-internal` version suffix so it cannot be mistaken for the production application. An APK that merely has “release” in its filename may still have incorrect signing; inspect the certificate rather than relying on the name.

The internal **FitOps QA** app preloads synthetic records once into a separate QA database. Production release builds force QA mode off and do not preload demo records. Follow the [screenshot workflow](qa-screenshots.md), keep demo labels visible, and describe synthetic captures as representative UI data rather than live Huawei data.

Internal builds target `arm64-v8a` by default for the current physical test phone. To test another Android CPU architecture, set `FITOPS_ANDROID_ARCHITECTURES` to the required comma-separated ABI list before `npm run build:internal`. Production release builds use the generated release architecture defaults and do not inherit that internal-only override. The native build plugin currently limits Gradle to a 4 GB heap, 1536 MB metaspace, and four workers; allow appropriate local build resources.

Current physical-device evidence: the latest bundled QA APK was installed on an RMX3851 running Android 16, its synthetic preload/startup/navigation were exercised, and three labelled native screenshots were captured. The production-mode arm64 unsigned candidate also built with QA mode disabled. The [verification record](verification.md) identifies both artifacts and their hashes. This does not check off physical file-picker/import/export checks, production signing, update behavior, or store publication.

The owner supplies an absolute `FITOPS_KEYSTORE_PATH`, `FITOPS_KEYSTORE_PASSWORD`, `FITOPS_KEY_ALIAS`, and `FITOPS_KEY_PASSWORD` through the local environment or a secure build system. Never commit the keystore, passwords, or signing configuration containing secrets. Preserve and back up the owner-managed release key for later updates. Do not print passwords in build logs or shell commands stored in documentation.

Before store upload:

- [ ] Verify the release signing implementation and artifact paths against the current build scripts.
- [ ] Generate or choose the owner's durable release signing identity; do not substitute the debug key.
- [ ] Build the candidate release, verify its signing certificate with Android `apksigner verify --print-certs`, and record the certificate fingerprint privately with the release evidence.
- [ ] Inspect application ID, version code/name, permissions, and bundled assets in the actual APK.
- [ ] Install the release candidate on intended Android hardware and verify that it launches with Metro stopped and no development server available.
- [ ] Verify an update using the same production signing identity preserves the local library.

Huawei's [APK release instructions](https://developer.huawei.com/consumer/en/doc/app/agc-help-releaseapkrpk-0000001106463276/) describe the package/listing submission. Register the correct release certificate fingerprint for native HMS integration when Huawei access is added; the internal/debug fingerprint does not establish the production identity.

## 4. Prepare a truthful store listing and public policies

- [ ] Publish an accessible privacy-policy URL whose text matches this Android release. Candidate documentation path: `https://brunov21.github.io/FitOps-CLI/legal/mobile-privacy` after deployment and verification.
- [ ] Verify the actual applying developer/controller identity and privacy/support contact. Replace any owner placeholders in internal materials before submission.
- [ ] Explain local SQLite storage, file imports, calibration, calculated estimates, deletion, and user-selected unencrypted exports.
- [ ] Explain that the user-selected share destination may upload the export according to that destination's settings. Do not claim data can never leave the device.
- [ ] Declare only permissions/SDK behavior found in the built APK. Update the policy and permission declaration before adding Huawei SDKs or any other data processing.
- [ ] Prepare the app icon, category, age/content rating, languages, target countries, concise description, and release notes.
- [ ] Capture screenshots from the real Android app: populated Overview, activity detail with method/coverage, zone calibration/boundaries, and privacy/appearance settings. Avoid personal data; use disclosed synthetic examples where suitable.
- [ ] Provide a supported sample TCX file and exact reviewer steps. No app account is required for the initial file-based version.

Use the prepared [English listing copy](../release/listing.en.md) and [reviewer walkthrough](../release/reviewer-instructions.md), then verify every advertised feature against the signed production candidate. The walkthrough supplies a synthetic TCX and explicit calibration/results without requiring a reviewer account.

Huawei's [app function requirements](https://developer.huawei.com/consumer/en/doc/app/50104-03) expect complete, working advertised features. Do not label an incomplete feature as available to satisfy the listing.

## 5. Obtain AppGallery release evidence

- [ ] Upload the verified, correctly signed production APK to the intended app record.
- [ ] Complete the listing, privacy disclosures, reviewer information, supported devices, countries, and scheduling in AppGallery Connect.
- [ ] Submit for review, resolve any findings, and obtain actual **Released** status.
- [ ] Save the public AppGallery listing URL, app ID, package name, release version/date, and released-status evidence.

A sideloaded APK, internal build, successful local build, GitHub download, test upload, or pending store review does not satisfy the release proof requested in Huawei's rejection.

## 6. Resubmit the Health Kit application

Use the [reapplication draft](huawei-reapplication.md). Attach the released listing and correct all four points in the [rejection](../../docs/providers/huawei/huawei-health-team-response.md). Do not claim a successful Huawei self-test while access is pending. Huawei test/formal permissions and approval for the disclosed mobile-to-desktop scenario remain separate from store release.
