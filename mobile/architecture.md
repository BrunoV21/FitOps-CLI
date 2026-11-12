# FitOps Mobile architecture

Status: initial architecture and design scaffold, 2026-11-12. Android first; native HarmonyOS is deferred. Product and Huawei approval details live in the [provider plan](../docs/providers/huawei/mobile-appgallery-plan.md).

## Product boundary and v1

FitOps Mobile is an independent local-first application. Its database, analytics, settings, and activity browsing work without a desktop installation or FitOps cloud account. Desktop and mobile share concepts, canonical data, and selected features, with intentional platform-specific functionality. Desktop CLI/dashboard parity remains required for desktop features.

V1 includes:

1. Athlete calibration: maximum HR, resting HR, LTHR where known, method selection, input provenance, sport applicability, and calibration date.
2. Heart-rate zones: explicit method and boundaries, validation, time in zones from timestamped samples, and honest missing-data states. Manual confirmed thresholds suffice; automatic threshold detection is deferred.
3. Per-activity TSS estimates with method, calibration dependency, and data quality visible.
4. Running VO₂max estimates with date, simple history, method/source, and suitability/confidence information. Provider estimates remain distinct from FitOps estimates.
5. Supported activity-file import, deduplicated local persistence, minimal activity history/details, offline metrics, and deletion.
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

Do not bring across GitHub authentication, financial models, OCR, private records, environment files, signing files, project IDs, or native application identity. Current scaffold reuses patterns only. If implementation code is copied or adapted, retain the reference project's MIT attribution in `THIRD_PARTY_NOTICES.md` alongside the copied code.

## Runtime choice

Use React Native with TypeScript and Expo Router, following the reference structure. Native Huawei integration requires an Android development/release build; Expo Go is not the target for that integration. Verify the reference Expo/React Native combination against the Huawei Health plugin and supported native SDK before pinning versions. Do not copy the reference lockfile or assume its dependency versions are compatible.

Prefer a native build/configuration workflow that can reproduce HMS configuration. A small Kotlin bridge under `modules/huawei-health/` is an escape hatch if the official plugin lacks required APIs. The first spike must establish which path works, including release signing, activity details, and intended devices. Build tooling and native directories are intentionally not generated yet.

## Directory structure

```text
mobile/
  README.md
  architecture.md
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

Empty implementation directories contain `.gitkeep` files. Future app configuration, package manifest/lockfile, test/lint settings, and Android build configuration belong under `mobile/`, independently of Python packaging.

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

Keep Huawei access/refresh tokens in Android-backed secure storage and out of exports, ordinary preferences, screenshots, and logs. Use preferences storage for theme choice only, not activity streams or credentials. Schema migrations run once at app initialization, never during render or repository reads. Import writes are transactional and restart-safe.

Mobile and desktop use separate local databases. The exchange format contains records, not whole SQLite files. Preserve provider, provider-account namespace, original activity ID, explicit units, UTC timestamps/timezone, available samples, source update time, and schema/calculation provenance. Reimport must be idempotent. Define deletion behavior before implementing it; exported records are snapshots, not automatic synchronized replicas.

Desktop imports records, not Huawei credentials. Huawei approval must explicitly cover the disclosed mobile-to-desktop flow. The mobile release does not imply desktop REST authorization. File-based handoff comes first; encrypted paired LAN transfer is deferred.

## Calculation correctness and caching

Existing reference modules are `fitops/analytics/zones.py`, `training_load.py`, and `vo2max.py`. Review their assumptions before porting. React Native does not directly run Python; use TypeScript implementations verified with shared synthetic reference cases, not duplicated formulas inside screens.

Results carry method/version, input availability, calibration version, units, and source. Do not silently swap zone methods or report a generic HR-based TSS estimate as equivalent to a power-based calculation. A VO₂max estimate must have a qualifying activity and sufficient inputs; unsupported data returns an explicit unavailable reason.

Calculate during import and explicit/background calibration updates. Persist results and invalidate affected caches when thresholds or methods change. Establish retrospective calibration policy before implementation. Read paths display cached results only. Metric reference cases cover boundaries, missing/gapped streams, zero duration, invalid calibration, unsuitable activities, and Python/TypeScript consistency.

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

1. Review mockups and v1 scope; settle import format and supported sports/methods.
2. Prove Expo/native Huawei compatibility on intended Android hardware before locking dependencies. Huawei calls require appropriate test authorization; build/configuration checks can precede it.
3. Scaffold the executable application with the verified dependencies; adapt the reference UI/theme patterns with attribution where code is copied.
4. Implement storage, calibration, and pure calculations with shared reference tests, then file import and core screens. Verify offline use and independent operation.
5. Verify both themes, text scaling, touch targets, screen-reader labels, actual contrast, metric empty states, and Android back/keyboard behavior. Unit tests are not a substitute for device checks.
6. Publish the useful file-based app, resubmit Huawei materials, and add approved Huawei import. Validate deduplication, scope/error handling, revocation, and deletion with offline test doubles.
7. Implement versioned export and desktop CLI/dashboard import with schema-validation and idempotence tests; update official product documentation as features ship.

The scaffold itself needs only file/link/token and diff checks. Runtime tests, native builds, device checks, and Huawei approval are pending implementation, not completed validations.
