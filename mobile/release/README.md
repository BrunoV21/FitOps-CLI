# AppGallery reviewer materials

These materials describe the independently useful, file-based FitOps Android app. They are prepared for review, not evidence of a public release or Huawei permission approval.

| Material | Ready-to-review content |
|---|---|
| English listing | [Short and full listing copy](listing.en.md) |
| Reviewer walkthrough | [Empty-library setup, synthetic import, and expected results](reviewer-instructions.md) |
| Sample activity | [TCX fixture](../../docs/official/public/mobile/fitops-reviewer-sample.tcx), copied unchanged from the shared synthetic reference |
| Native screenshots | [QA capture metadata](../docs/screenshots/qa/README.md), [Overview](../docs/screenshots/qa/01-overview-dark.png), [Activities](../docs/screenshots/qa/02-activities-dark.png), [Zones](../docs/screenshots/qa/03-zones-dark.png) |
| Production privacy notice | [Android notice source](../../docs/official/legal/mobile-privacy.md); publish and verify its public URL before submission |
| Production candidate | [Local unsigned arm64 APK](../artifacts/fitops-0.1.0-arm64-unsigned.apk); owner signing and final identity checks are still required |
| Recorded build evidence | [Artifact hashes and verification scope](../docs/verification.md) |

The screenshot app is **FitOps QA**, with the visible **QA · DEMO DATA** label. Those native captures use synthetic records to illustrate the UI. **Never upload the QA APK as the production release.** The release candidate has QA mode disabled, starts without the preloaded examples, and needs the reviewer sample imported manually.

The provisional production package is `app.fitops.mobile`. Confirm its mapping to the owner's Huawei app ID `117915041` and use the owner's durable signing identity before upload. The unsigned APK is a local build artifact, not an installable/public store release.

No countries, legal applicant identity, account type, private contacts, release date, or released listing URL are filled by this material. The owner must supply the actual values from the account and final release. Follow the [release checklist](../docs/appgallery-release.md) for those remaining gates.

After the correctly signed production app reaches actual **Released** status on AppGallery, attach its listing/status evidence to the [Health Kit reapplication draft](../docs/huawei-reapplication.md). Native screenshots, an unsigned build, and this material pack do not replace the release proof Huawei requested.
