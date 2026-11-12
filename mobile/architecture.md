# FitOps Mobile architecture

Status: Android MVP implementation, 2026-11-12; native build/device verification and store publication are separate gates. Android first; native HarmonyOS is deferred. Product and Huawei approval details live in the [provider plan](../docs/providers/huawei/mobile-appgallery-plan.md), [release checklist](docs/appgallery-release.md), and [reapplication draft](docs/huawei-reapplication.md).

## Product boundary and v1

FitOps Mobile is an independent local-first application. Its database, analytics, settings, and activity browsing work without a desktop installation or FitOps cloud account. Desktop and mobile share concepts, canonical data, and selected features, with intentional platform-specific functionality. Desktop CLI/dashboard parity remains required for desktop features.

V1 includes:

1. Athlete calibration: maximum HR, resting HR, LTHR where known, method selection, input provenance, sport applicability, and calibration date.
2. Heart-rate zones: explicit method and boundaries, validation, time in zones from timestamped samples, and honest missing-data states. Manual confirmed thresholds suffice; automatic threshold detection is deferred.
3. Per-activity TSS approximations with method, calibration dependency, and missing-data states visible. The initial methods are HR- and running-pace-based stress approximations, not normalized-power TSS or a proprietary hrTSS implementation.
4. Running VO₂max estimates with date, simple history, method/source, and suitability/missing-data information. This initial Daniels running-performance proxy has no validated statistical confidence score and is not a laboratory measurement. Imported provider VO₂max estimates are not part of the version-1 exchange.
5. TCX and FitOps JSON activity-file import, deduplicated local persistence, minimal activity history/details, offline metrics, and deletion.
6. Selected-record export in a versioned format, followed by optional desktop import through CLI and dashboard. Huawei read-only import is added after approval; publication and Health Kit authorization are separate milestones.

Deferred: training-session planning and compliance, form/TSB, CTL/ATL, readiness/recovery, coaching, race tools, advanced power/weather analysis, live recording, wearables, automatic calibration, paired network transfer, bidirectional sync, cross-provider duplicate merging, iOS, and native HarmonyOS.

## Reference project and reuse

The local reference is `../BranchBalance`. Inspected sources include `package.json`, `src/app/_layout.tsx`, `src/components/ui/index.tsx`, `src/providers/theme-provider.tsx`, storage contracts/credential adapters, test setup, and the HTML mockup workflow.

| Reference | FitOps adaptation |
|---|---|
| Expo Router and thin `src/app` routes | Keep routing separate from feature screens and business logic. |
| `src/features`, `src/domain`, `src/infrastructure` | Retain those boundaries with fitness-specific modules. |
| Theme context and persisted system/light/dark preference | Reuse the pattern with FitOps tokens and a dedicated preferences adapter. |
| `Screen`, `Button`, `Field`, `Banner`, `ConfirmDialog`, `EmptyState` | Adapt safe-area, keyboard, accessibility, loading, and confirmation behavior; replace serif typography, rounded surfaces, and financial styling. |
| Storage interfaces with memory/secure adapters | Reuse dependency-injection patterns; use SQLite for fitness records and secure storage for Huawei credentials. |
| Colocated domain/component tests and shared test setup | Retain organization, replacing GitHub mocks with local import/provider fixtures. |
| Standalone HTML/CSS/JS mockups | Use a dependency-free visual design workspace before native screens. |

Do not bring across GitHub authentication, financial models, OCR, private records, environment files, signing files, project IDs, or native application identity. Theme-provider, application-composition, and UI primitive patterns have been adapted; the reference project's MIT attribution is retained in `THIRD_PARTY_NOTICES.md`.

## Runtime choice

Use React Native with TypeScript and Expo Router, following the reference structure. The initial app uses Expo SDK 57 and React Native 0.86, with exact versions in its own manifest and lockfile. Native Huawei integration requires an Android development/release build; Expo Go is not the target for that integration. The current package does not contain the Huawei Health SDK/plugin. Its compatibility must be established before adding Huawei access; the file-based app does not prove that compatibility.

Expo prebuild/native Android builds provide the initial build workflow. A small Kotlin bridge under `modules/huawei-health/` remains an escape hatch if the official plugin lacks required APIs. The Huawei integration spike must establish which path works, including signing identity, approved activity details, and intended devices. The application package is provisionally `app.fitops.mobile`; verify it against app ID `117915041` before store registration or HMS configuration.

## Directory structure

```text
mobile/
  README.md
  architecture.md
  docs/                    AppGallery release checklist and Health Kit reapplication draft
  mockups/                 HTML/CSS/JS proposals; synthetic data only
  assets/                  FitOps icons and approved bundled font assets
  contracts/
    transfer/              Versioned mobile/desktop exchange schemas
    fixtures/              Synthetic canonical and formula reference cases
  modules/
    huawei-health/         Optional native bridge; reserved until spike
  scripts/                 Build, fixture verification, and release helpers
  src/
    app/                   Thin Expo Router routes/layouts
    components/ui/         Theme-aware accessible primitives
    theme/                 Semantic palette, spacing, type, chart tokens
    providers/             Theme and application dependency contexts
    domain/
      activities/          Canonical records and identity
      calibration/         Threshold provenance and validation
      analytics/           Pure zones, TSS, VO₂max functions
    features/
      overview/            Core metric summary
      activities/          Local history and activity detail
      zones/               Zone calibration and breakdown
      settings/            Appearance, privacy, and data controls
      imports/             File/Huawei import progress and results
      exports/             Selection and explicit data export
    infrastructure/
      storage/             SQLite repositories, migrations, preferences
      providers/huawei/    Approved Huawei adapter and credential access
      imports/             File parsing adapters
      transfer/            Exchange serializer/validator
    test/                  Test setup and synthetic adapters
```

Runtime modules, app configuration, the package manifest/lockfile, and test/lint settings live under `mobile/`, independently of Python packaging. Remaining reserved directories contain `.gitkeep` files until their corresponding integration is implemented.

## Internal QA mode

`app.config.js` derives `extra.qaMode` from `FITOPS_QA_BUILD`. The internal build script forces it on and names the launcher **FitOps QA**; production release builds force it off. The internal variant has a separate `.internal` package identity and uses `fitops-mobile-qa.db` rather than the production database.

The QA provider seeds three deterministic synthetic runs and labelled sample calibration once on first launch. A global demo badge identifies synthetic library records. `QA library` offers a confirmed replacement of the QA library with the fixtures; clearing the library does not silently reseed it on restart. No live Huawei data is involved. Production operation does not preload demo records or expose the QA controls. See the [QA screenshot workflow](docs/qa-screenshots.md) for expected fixture values and honest screenshot labelling.

## Dependency and data flow

Routes → feature controllers/screens → domain functions and repository contracts. Infrastructure implements contracts and is injected at app composition. Domain code imports neither React nor native SDKs; UI never calls Huawei or executes SQL directly.

```text
File parser / approved Huawei adapter
                ↓
Canonical validation + account/provider identity
                ↓
Import use case → SQLite activities and samples
                ↓
Calculation jobs + calibration version → cached derived metrics
                ↓
Repository reads → feature view models → mobile screens
                ↓ explicit user selection
Versioned export → desktop import adapter → desktop DB → CLI/dashboard
```

No Huawei credentials are used by the initial app. When Huawei integration is implemented, keep access/refresh tokens in Android-backed secure storage and out of exports, ordinary preferences, screenshots, and logs. Appearance uses preferences storage; activity records, samples, calibration, and cached metrics use SQLite. Schema initialization runs once at app initialization, never during render or repository reads. Import and calibration updates use database transactions.

Mobile and desktop use separate local databases. The version-1 exchange contains canonical activity records, not whole SQLite files or metric caches. It includes provider, provider-account namespace, original activity ID, sport, timestamp with timezone offset, elapsed duration, distance, and available time/HR/distance/speed samples. The envelope records schema version and export time. Local IDs are recomputed from provenance on import. Separate source-update timestamps, GPS, laps, granted-scope metadata, calibration profiles, and imported provider metrics are not in this version. Reimport updates matching identities. Exports are snapshots; deleting a record on one device does not delete copies elsewhere.

Selected exports are unencrypted JSON shared only after explicit confirmation. They contain sensitive fitness data and must go to a destination chosen by the user. Do not describe this first export as end-to-end encrypted or automatically paired. The app disables Android app backup and does not configure a FitOps cloud account, advertising, analytics tracking, or automatic uploads. The release manifest and runtime still need device verification against these intended properties.

Shared JSON files remain in the app's temporary export cache after the chooser returns so the receiving app can still read them. Files older than 24 hours are removed on a best-effort basis at the next app startup or export; this is not a scheduled 24-hour deletion guarantee. Erasing the local library also clears the local export cache. Copies already received by other apps or saved destinations are unaffected.

Desktop imports records, not Huawei credentials. Huawei approval must explicitly cover the disclosed mobile-to-desktop flow. The mobile release does not imply desktop REST authorization. File-based handoff comes first; encrypted paired LAN transfer is deferred.

## Calculation correctness and caching

Existing reference modules are `fitops/analytics/zones.py`, `training_load.py`, and `vo2max.py`. React Native does not directly run Python. Mobile calculations live in pure TypeScript domain functions; shared reference cases must verify the formulas offered on both runtimes. Mobile intentionally does not inherit desktop fallback assumptions that invent intensity when calibration is absent.

Results carry method/version, input availability, calibration version, units, and source. Do not silently swap zone methods or report a generic HR-based TSS estimate as equivalent to a power-based calculation. A VO₂max estimate must have a qualifying activity and sufficient inputs; unsupported data returns an explicit unavailable reason.

Calculate during import and calibration updates, then persist the results. Saving calibration retrospectively recalculates every saved activity for the same sport in the same transaction. Removing calibration invalidates dependent estimates. Read paths display cached results only. Metric reference cases cover boundaries, missing/gapped streams, zero duration, invalid calibration, unsuitable activities, and Python/TypeScript consistency.

Initial calculation rules:

- HR zones support LTHR, HR reserve, and maximum HR, using sport-specific manual inputs. Bounds are lower-inclusive/upper-exclusive; below-Zone-1 HRR/max-HR intervals are unclassified.
- Time in zones uses measured HR intervals only. Intervals longer than 30 seconds are excluded, and the last sample is not extended to fill missing time.
- Stress is `elapsed_hours × intensity² × 100`. Running uses average-speed/threshold-speed when threshold pace is provided. Otherwise an LTHR-based approximation uses measured average HR/LTHR with at least 80% HR coverage. Method and calibration version accompany the cache.
- The initial running VO₂max proxy uses the Daniels pace model on qualifying near-threshold continuous segments. It requires at least 10 continuous minutes and 1.5 km in total, suitable HR/speed samples, and a running LTHR or maximum-HR reference. The UI explains unavailable results and model limitations; it must not imply a clinical measurement or calibrated confidence probability.

## Design system: FitOps on a phone

Source identity: `fitops/dashboard/static/css/main.css`, the terminal-brutalist dashboard. Preserve neon green `#00ff87`, black surfaces, monospace typography, squared geometry with restrained corner rounding, thin rules, and blue/amber/red/purple supporting colors. Adapt the layout and density for touch rather than shrinking desktop tables.

`src/theme/tokens.json` holds the initial semantic colors and sizing. Dark palette comes from the dashboard; light palette is a new proposed adaptation. Use deeper green/blue/status colors for readable text on light surfaces while keeping the recognizable neon green for filled actions with black text. Validate actual text/background pairs before native UI acceptance.

- Appearance choices: System (default), Light, Dark. Persist the preference, react to system changes only in System mode, and style system bars consistently.
- Navigation: a floating liquid-glass header with a squared, softly rounded section picker shows the current section and opens an on-demand menu for Overview, Activities, Zones, and Settings. Use translucent blur, subtle highlights, an animated menu, and light/dark variants. Respect reduced motion and provide opaque fallbacks when blur is unavailable or reduced transparency is requested. No persistent bottom bar. Import lives in Activities; export lives in activity selection/data controls. Avoid a desktop sidebar.
- Use a consistent squared glass treatment throughout the mobile UI: 16px header/menu corners, 12px cards, and 8px nested controls/notes. Avoid pill shapes. Keep 1 logical-pixel borders, subtle surface highlights, and restrained elevation. Content panels are more opaque than navigation and avoid per-card backdrop blur to preserve readability and rendering performance. Native Android blur support and rendering cost must be checked; use a theme-aware opaque fallback where needed. Give controls at least 48 logical pixels of touch height and clear pressed/disabled/focus states.
- Start with Android monospace; a bundled Geist Mono/JetBrains Mono font can follow once licensing and asset loading are checked. Use 16px-equivalent body text, readable line heights, prominent metric numerals, and dynamic text sizing without clipped labels.
- Use vertical cards and short labelled rows. Respect safe areas, keyboard avoidance, Android back behavior, small screens, and screen readers.
- Every chart has units, a textual summary, and a data-list equivalent. Zone labels and status text accompany colors. Respect reduced motion and avoid animated metric decoration.
- Explicit states: empty library, importing, partial samples, calibration needed, no qualifying VO₂max run, denied/revoked Huawei permission, failed import, offline, and complete data. No placeholder score masquerades as a calculated result.

## Mockup workflow

The initial browser mockup presents Overview, Activities, Zones, and Settings, including theme controls. It uses synthetic values and does not implement metric calculations, import, export, persistence of health records, or authorization. Its CSS/JS is preview-only and must not become a WebView app wrapper.

Next design passes should add activity detail, import review, export confirmation, calibration editing, and the missing-data/error states listed in `mockups/README.md`. Keep labels and token values aligned with native components; visual approval is separate from formula validation.

## Delivery and verification

1. Finish verification of file imports, local storage, calibration, and the three core metrics against reference fixtures and UI tests.
2. Build the independently useful Android app and verify it on intended hardware, including offline launch, both themes, large text, screen readers, import/export, deletion, and Android back/keyboard behavior.
3. Verify selected-record export and desktop CLI/dashboard import with schema validation, identity preservation, and idempotence tests. Add official user documentation as behavior is implemented.
4. Verify final owner-controlled package/signing identity and publish the useful file-based app. Capture production AppGallery release evidence, not merely a debug/internal APK.
5. Resubmit Huawei materials with the actual release, least-privilege requests, and the disclosed optional desktop data flow.
6. After approval, establish Expo/native Huawei compatibility on intended hardware, implement approved reads, and test scope/error handling, consent/revocation, persistence, and the permitted export flow before releasing the Huawei-enabled update.

The runtime has TypeScript domain/import/repository tests, including real in-memory SQLite repository tests. Passing test counts, native build success, physical-device results, screenshots, and release signing are evidence to collect from actual runs, not claims established by this document. The [release checklist](docs/appgallery-release.md) separates implementation from verification, AppGallery publication, and later Huawei permission approval.
