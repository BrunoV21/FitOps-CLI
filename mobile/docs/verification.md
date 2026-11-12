# Android MVP verification record

Recorded: 2026-11-12. This is evidence for the current working-tree build based on commit `73518e2`; the implementation has not been committed as a new release. These artifacts and checks do not establish production signing, AppGallery publication, or Huawei authorization.

## Built artifacts

| Artifact | Identity and status | SHA-256 |
|---|---|---|
| `mobile/artifacts/fitops-qa-0.1.0-arm64.apk` | Bundled, debug-signed internal QA app; `app.fitops.mobile.internal`, `0.1.0-internal`, launcher **FitOps QA** | `70fe2bb5b183231f7a64942017de23008e4809cec9477593ebd4ff537e699780` |
| `mobile/artifacts/fitops-0.1.0-arm64-unsigned.apk` | Unsigned production candidate; `app.fitops.mobile`, `0.1.0`, launcher **FitOps** | `c5284e47b600b667168ba654a5f9cc56efa6052fb036204b49207e1953628499` |

Both files are approximately 42 MB and target arm64 for this validation. Hashes can be rechecked with `shasum -a 256 mobile/artifacts/*.apk` from the repository root. APKs are local build outputs, not committed store downloads.

Inspection of the embedded `assets/app.config` confirms **FitOps QA / qaMode=true** for the internal artifact and **FitOps / qaMode=false** for the production candidate. The production identity has no internal suffix; the release still requires the owner's verified final package registration and production signing key.

## Completed evidence and its scope

- The latest bundled QA APK was installed on an RMX3851 running Android 16.
- Native startup, labelled synthetic preload, and section navigation were exercised on that phone. The three deterministic demo records and synthetic running calibration were available for capture.
- The system file picker selected the synthetic TCX fixture; native review/save imported its 181 samples successfully (1 created, 0 updated). Repeating the same file import reported 0 created, 1 updated.
- Selecting a demo record and confirming export opened Android's native share chooser. The chooser was cancelled without selecting a recipient; no record was sent to another application/service. Recipient-side JSON reading remains a separate check.
- The QA library reload confirmation restored the bundled examples. After force-stopping and reopening the app, the cached 43.6 running estimate and demo library persisted.
- Three native dark-mode screenshots were captured: [Overview](screenshots/qa/01-overview-dark.png), [Activities](screenshots/qa/02-activities-dark.png), and [Zones](screenshots/qa/03-zones-dark.png). Each is a 1080 × 2376 PNG below 200 KB. The [screenshot metadata](screenshots/qa/README.md) records the app identity and capture context.
- The implementation task's latest automated baseline passed TypeScript checks, lint, and 48 Jest tests. The relevant Python baseline passed 60 tests, covering the mobile exchange/reference work and affected desktop import paths. These counts describe those runs, not every test in the repository or later edits.
- The production arm64 unsigned candidate completed its native build. An unsigned artifact cannot be installed as the public release or submitted as a correctly signed production APK.

Re-run `npm run validate` from `mobile/` and the affected Python tests after runtime changes; a prior green baseline does not validate a different artifact. VitePress documentation builds and link checks are tracked separately from native/device checks.

## Still required

- [ ] Additional physical-device coverage with a user-provided recorded TCX and a FitOps JSON file; the synthetic TCX path is verified above.
- [ ] Physical-device export through Android sharing, verifying the chosen recipient reads the complete JSON after the chooser closes.
- [ ] Additional device coverage for retrospective calibration edits, individual deletion, erasure remaining empty after restart, and network-disabled operation. Synthetic deduplication, explicit demo reload, and process-restart persistence are verified above; transactional recalibration/erasure also have automated SQLite tests.
- [ ] Light-mode screenshots and representative accessibility/large-text/keyboard checks on the final candidate.
- [ ] Final production package/account mapping, owner-managed release signing, production install/update verification, and public policy deployment.
- [ ] AppGallery submission and actual Released-status evidence.
- [ ] Huawei permission approval, native SDK integration, and live authorization/data/self-tests after access is granted.

The verified native import/export-chooser and persistence checks used synthetic records. Further recipient-side, accessibility, production-signing, and live-Huawei checks remain explicitly unclaimed.
