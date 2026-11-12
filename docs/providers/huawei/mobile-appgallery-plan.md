# FitOps Mobile, AppGallery, and Huawei Data Transfer

Research checked: 2026-11-12. This is a proposal, not a shipped integration or an assurance of Huawei approval.

## Product direction

FitOps Mobile is an independent, local-first fitness app. It has its own database, imports, activity views, and useful analytics. It works without a desktop installation. Desktop and mobile share goals, data contracts, and selected functionality; platform-specific features are intentional.

The in-repository mobile workspace is [`mobile/`](../../../mobile/README.md), with its [architecture](../../../mobile/architecture.md) and [UI mockups](../../../mobile/mockups/README.md). It follows reusable patterns from the local `../BranchBalance` React Native project while retaining FitOps branding.

Desktop can optionally import Huawei-origin data that the user has authorized FitOps Mobile to read and explicitly chosen to transfer. Mobile remains useful when no desktop is paired. Desktop remains useful when no phone is connected.

The existing CLI/dashboard parity rule still applies to desktop features. It does not require a CLI on the phone or every desktop feature on mobile. Mobile-to-desktop imports must be available through both desktop interfaces when implemented.

## What Huawei has actually required

The [rejection for app ID 117915041](./huawei-health-team-response.md) asks for AppGallery release evidence, one historical dataset permission, justification for yearly history if requested, removal of unnecessary sport ability/achievement permissions, and completion of the form's blue example text.

Publication and Health Kit authorization are separate approvals. A published app is not automatically entitled to health data or desktop REST access.

The exact qualification URL in the rejection did not yield usable policy text during this research. Huawei's separate [HarmonyOS Health Service Kit application guide](https://developer.huawei.com/consumer/en/doc/harmonyos-guides/health-apply/) explicitly requires a released mobile app for individual applicants and limits their data openness. That is corroborating context, not proof that every HarmonyOS condition applies to our Android application. Confirm the registered account type and applicable Android rules with Huawei.

## Package and framework

| Target | Distribution artifact | FitOps implication |
|---|---|---|
| Android / compatible EMUI devices | Signed APK; AAB is another supported route | React Native Android is a viable candidate. |
| Native HarmonyOS NEXT | HarmonyOS APP release package | A standard React Native Android APK does not provide this target; evaluate separately if needed. |
| Desktop | Existing Python distribution | AppGallery mobile publication does not replace desktop packaging. |

Huawei distinguishes [APK, AAB, APP, and quick-app release formats](https://developer.huawei.com/consumer/en/doc/app/agc-help-release-overview-0000001272395372/). Its [migration guide](https://developer.huawei.com/consumer/en/doc/harmonyos-guides/app-data-migration-overview/) describes switching APK apps to HarmonyOS apps on NEXT.

Huawei publishes an official [React Native Health plugin](https://developer.huawei.com/consumer/en/doc/HMS-Plugin-Guides-V1/introduction-0000001050155802-V1/) and [plugin source](https://github.com/HMS-Core/hms-react-native-plugin). This supports choosing React Native, but does not establish compatibility with whichever React Native version, architecture, SDK version, and phones we select. First run a small native build/integration spike, then pin the verified versions. If required APIs are missing from the plugin, evaluate a small Kotlin bridge to the supported native SDK.

V1 platform decision: React Native Android, distributed as a signed APK through AppGallery. A native HarmonyOS version is deferred. Validate actual device/region support rather than promising all Huawei phones or all Android phones.

## Agreed Android v1 feature scope

The first version prioritizes trustworthy TSS, VO₂max estimates, and correctly configured/calibrated heart-rate zones. Training-session planning, training form, and broader coaching features can wait. The app must perform its core functions on the phone without a desktop or FitOps cloud account.

| Feature | Required v1 behavior |
|---|---|
| Athlete calibration/settings | Let the user enter and correct maximum heart rate, resting heart rate, and lactate-threshold heart rate where known. Record the source, sport applicability, and date of calibration; distinguish user-confirmed inputs from estimates/defaults. |
| Heart-rate zones | Show the selected zone method, the inputs it uses, and clearly labelled boundaries in beats per minute. Support the existing FitOps LTHR, heart-rate-reserve, and maximum-HR methods where their required inputs are available. Explain missing calibration inputs rather than silently substituting another method. |
| Zone breakdown | Show time in each zone for activities with usable timestamped HR samples. Account for gaps and missing samples; do not invent a zone distribution from average HR. |
| Activity TSS | Show per-activity training-stress estimates, with the calculation method and required threshold inputs visible. Clearly distinguish HR-based estimates from other methods; missing inputs must produce an unavailable/needs-calibration state rather than a misleading score. |
| VO₂max estimate | Show the latest supported running estimate and a simple history, in ml/kg/min, with source/method, confidence or data-quality status, and estimate date. Distinguish FitOps estimates from any imported provider estimate. Exclude unsuitable activities and explain when there is insufficient data. |
| Activity import and storage | Import a supported file format before Huawei approval; add read-only Huawei import after permission approval. Persist activities and required samples locally, preserving provider identity and preventing repeat imports from creating duplicates. |
| Minimal activity browser | List imported activities and open basic details: sport, date, distance, duration, available HR/pace samples, TSS, and zone breakdown. This is history viewing, not a training-session planner. |
| Minimal home screen | Show the current zone calibration, latest VO₂max estimate/date, and recent activity TSS values. Handle no activities, no qualifying runs, and missing HR data explicitly. |
| Data control and desktop handoff | Provide local deletion and explicit export of selected activities and available samples. Include a versioned FitOps export for optional desktop import; phone operation must not depend on pairing. Desktop import is exposed through both CLI and dashboard when delivered. |

### Calibration and calculation acceptance criteria

- Validate calibration inputs and zone ordering. Label estimated thresholds as estimates; do not claim physiological calibration from an age-based default or an unvalidated automatic detector.
- Manual entry of known/test-derived thresholds is sufficient for v1. Automatic threshold detection, guided field tests, and adaptive calibration are deferred unless required to make the agreed core usable.
- Define and review the exact TSS and VO₂max methods before porting them. Existing Python implementations are starting points, not proof that the calculations are correct for every sport or input quality.
- For methods offered in both runtimes, use shared reference fixtures to verify Python/TypeScript agreement, including missing data, zero duration, timestamp gaps, zone boundaries, and non-qualifying VO₂max activities.
- Save calculation method/version and calibration provenance with derived results. Changing calibration must invalidate affected cached values and trigger an explicit/background recalculation, never expensive computation during screen rendering or desktop reads. State whether changes apply retrospectively.
- Compute and cache metrics during import or calibration updates. Viewing saved activities and metrics must work offline.
- A metric is complete only when required source data is demonstrably available through the selected import path. A file containing only route coordinates cannot satisfy HR-zone/TSS requirements by itself.

### Explicitly deferred beyond v1

- Training-session/workout creation, scheduling, plans, and compliance scoring.
- Training form (TSB), fitness/fatigue (CTL/ATL), readiness, recovery, and coaching recommendations. Per-activity TSS remains in scope.
- Race simulation, predictions, and race planning; advanced power, weather, and running-form analytics.
- Live workout recording, watch integration, and notifications.
- Automatic threshold detection and adaptive zone calibration.
- Native HarmonyOS, paired local-network transfer, bidirectional sync, and automatic cross-provider activity merging.

### Publication and Huawei-enabled release stages

The initial AppGallery release delivers the core features above using supported activity files with sufficient data. The Huawei-enabled update adds approved Huawei reads and exports the same canonical records to desktop. This is one product delivered in stages because Huawei requested release evidence before granting access; file-only publication does not complete the Huawei integration goal.

File import requires format selection and implementation; it is not an existing mobile capability. The import format must carry the time, HR, distance/speed, and other inputs required by the methods selected for v1. Sample data can help onboarding, but is not a substitute for a working product. Huawei functionality should only be advertised as available once approved and implemented.

Huawei's [app function rules](https://developer.huawei.com/consumer/en/doc/app/50104-03) require working, complete functionality and allow rejection of test-only or non-independent apps. An independent first release resolves the publication-before-health-approval dependency in principle; acceptance remains Huawei's decision.

## Mobile-to-desktop architecture

```text
Huawei Health / Health Kit
          |
          | approved read scopes + user consent
          v
FitOps Mobile provider adapter
          |
          v
Mobile canonical records + local database --> mobile views / analytics
          |
          | user-selected export, then optional paired local transfer
          v
Desktop import adapter --> desktop SQLite --> CLI + dashboard
```

Transfer data, not Huawei access tokens, refresh tokens, or client secrets. Desktop imports already-authorized records through a FitOps transfer format; it does not impersonate the mobile app against Huawei's API. This is the recommended technical boundary, not a claim that Huawei has already approved the scenario.

Start with an explicit file export/import. Add paired local-network transfer later if desired: desktop displays a short-lived pairing QR code, the phone confirms the recipient, and an authenticated encrypted channel carries selected records. Do not expose the existing desktop server on the LAN as an unauthenticated receiver. File exports also need clear handling of sensitive contents and an encryption design.

The first bridge should be one-way, mobile to desktop. Bidirectional sync would need additional conflict, deletion, and ownership rules and is not necessary to import Huawei data.

Define a versioned transfer contract with:

- Original provider (`huawei`), provider account namespace, and original activity ID. Transport (`mobile_export`) is separate provenance, not the provider identity.
- UTC timestamps, local timezone, explicit units, summary fields, and optional streams/laps.
- Data availability, granted data categories, export time, source changes, and transfer cursor/manifest.
- Idempotent imports, changed-record updates, account separation, and explicit deletion semantics.

Keep mobile and desktop databases separate. Exchange canonical records rather than whole SQLite files. Do not automatically merge similar Huawei and Strava activities; retain provenance until an explicit duplicate policy exists.

Share schema definitions, sanitized fixtures, and formula reference cases between Python and TypeScript. React Native does not automatically execute the existing Python analytics. For any metric implemented in both runtimes, test against the same reference cases; keep expensive computation off screen-render/read paths.

## Consent and Huawei review scope

Huawei documents [user data export](https://developer.huawei.com/consumer/en/doc/hms-guides/personal_dataprocess-0000001050069754/) and [authorized fitness data sharing](https://developer.huawei.com/consumer/en/doc/app/70941808/). The export page is dated 2019; neither source is specific approval for this architecture. Include optional transfer to the user's own FitOps Desktop in the application, data-flow diagram, privacy statement, and transfer consent. Ask Huawei to confirm it explicitly.

The CLI's agent interface also needs truthful disclosure: local tools or agents selected by the user can access imported desktop records. Do not promise that data never reaches another service if the user can intentionally send it there. Provider permissions do not authorize unrelated uses of the data.

Request only required read scopes. Huawei's [exercise-record guide](https://developer.huawei.com/consumer/en/doc/HMSCore-Guides/introduction-fitness-record-data-0000001131831088/) distinguishes record summaries (`activityrecord.read`), associated detail (`activity.read`), and routes (`location.read`). GPS access should be justified by the actual map/export features. Scope approval does not guarantee every watch supplies every stream.

Choose one historical access tier. A smaller tier can bootstrap a local archive accumulated over time, but only if the user synchronizes within that window; it cannot recover older records outside the approved history. Request yearly history only with a concrete initial-backfill need. Exclude sport ability and achievement from the first resubmission unless essential and separately justified.

## AppGallery distribution sequence

1. Confirm developer identity verification, account type, target countries, and the type/package configuration of existing app ID `117915041`. Do not assume a separate Android registration inherits its permission application.
2. Choose the final package name and release signing key. For native HMS integration, register the correct signing certificate SHA-256 fingerprint and configure the project using Huawei's [React Native setup guide](https://developer.huawei.com/consumer/en/doc/HMS-Plugin-Guides-V1/config-agc-0000001074109946-V1/).
3. Build and test the independently useful release on intended phones, including operation without a desktop.
4. In AppGallery Connect, upload the signed APK, select countries, and complete the listing, screenshots, category, content rating, privacy information, and reviewer instructions/access. Submit for review and obtain Released status and the listing URL. See [APK release instructions](https://developer.huawei.com/consumer/en/doc/app/agc-help-releaseapkrpk-0000001106463276/).
5. Resubmit the Health Kit request with release proof, corrected forms, limited permissions, and the full mobile/desktop data flow.
6. After the applicable development authorization, validate imports, missing data, revocation, deletion, and transfer behavior. Complete any required formal-permission review before general use, and release the Huawei-enabled app update through AppGallery.

An APK download on GitHub or a test upload is not the released AppGallery evidence requested in the rejection. Updates should use the store release process.

An AAB is optional: Huawei's [AAB guide](https://developer.huawei.com/consumer/en/doc/app/agc-help-releasebundle-0000001100316672/) describes App Signing and generation of device-specific APKs. Mainland China adds qualification requirements; choose it only if it is an intended launch market and prepare against the applicable [qualification rules](https://developer.huawei.com/consumer/en/doc/app/80301/).

## Questions for Huawei before committing to the bridge

Draft only; not sent:

> For FitOps, app ID 117915041, we plan an independent Android fitness app distributed on AppGallery. It will store user-authorized Huawei activity records locally and provide activity history and analytics without any desktop dependency. Users may optionally export selected records to their own local FitOps Desktop installation for further analysis through its dashboard and CLI, including user-directed local agent access. Huawei credentials remain on mobile. Does this architecture qualify, and what disclosure/consent or transfer restrictions apply? Can the Android release use this existing app ID, and which individual/enterprise, region, historical-access, and activity-detail restrictions apply? How should we obtain development/test permissions after publishing the initial app, and what formal approval is required for general availability?

## Next engineering milestones

1. Verify account/app configuration and obtain Huawei's answer on the proposed data flow.
2. Run the React Native/native SDK compatibility spike; confirm activity detail and scope coverage.
3. Specify the agreed TSS, VO₂max, and HR-zone MVP above, including calculation methods, import format, canonical exchange schema, and shared metric reference cases.
4. Build the independent mobile MVP and AppGallery materials.
5. Obtain release evidence and resubmit the corrected Health Kit application.
6. Implement approved Huawei import on mobile, then desktop file import through CLI and dashboard with tests and official docs.

The existing direct-REST provider plan remains an alternative requiring its own approval. It is not a dependency of the proposed mobile data bridge.
