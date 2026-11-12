# Health Kit reapplication draft

Draft only. Not submitted. Huawei sync is not implemented or approved in the initial Android app. Complete the fields below from actual release/account evidence before copying material into Huawei's current application template.

## Application identity and release proof

| Field | Value to verify or supply |
|---|---|
| Existing Huawei app ID | `117915041` — verify this is the Android app record to be reviewed |
| App name | FitOps |
| Android package | Provisional code value `app.fitops.mobile`; use the verified AppGallery registration value |
| Developer account type | `[OWNER: individual or enterprise, matching the registered account]` |
| Applying legal identity and contact | `[OWNER: exact registered identity and contact details]` |
| AppGallery listing URL | `[OWNER: public URL after Released status]` |
| Released version/date | `[OWNER: actual production version and release date]` |
| Countries/regions served | `[OWNER: exact countries selected for release and intended Huawei use]` |
| Public privacy-policy URL | `[OWNER: verify deployed Android-specific notice; candidate /FitOps-CLI/legal/mobile-privacy]` |
| Supporting release evidence | `[OWNER: AppGallery released-status screenshot or other proof Huawei requests]` |

Do not submit an internal/debug package suffix, debug certificate, HTML-mockup screenshot, or planned release date as production release evidence.

## Current product description

> FitOps is an independent, local-first Android fitness analytics application. Its initial release imports user-selected TCX and FitOps JSON activity files, stores the records and available heart-rate/pace samples in a local SQLite database, and provides activity history, sport-specific heart-rate calibration and zones, time in zones, per-activity stress approximations, and qualifying running VO₂max estimates. It works without a desktop installation or FitOps cloud account. Users control local deletion and may explicitly export selected records through Android sharing. Huawei Health synchronization is not available in this initial release; this application requests approval to implement that integration.

Use this paragraph only after the described first release has passed its actual tests and been published. FitOps stress and VO₂max results are fitness estimates, not medical diagnosis, treatment, or laboratory measurements.

## Proposed Huawei data use

> After Health Kit permission approval and user authorization, FitOps Mobile will read only the approved activity records and associated samples needed for its implemented fitness views. The intended first integration uses activity timing, sport, duration, distance, and available heart-rate/speed samples to populate the local activity library, heart-rate zone breakdowns, stress approximations, and running-performance estimates. Data will be processed locally on the user's phone. No write access, data resale, health-data advertising, or model training is requested.

> Users may separately choose to export selected activity records to their own FitOps Desktop installation. The desktop CLI and dashboard will analyze a local copy. Huawei access and refresh tokens will remain on mobile and will not be included in exports. Desktop transfer is optional and does not affect the mobile app's independent operation. The export is user-initiated, uses a versioned FitOps data format, and includes only the disclosed activity fields. The user can choose another share destination; FitOps explains that the resulting JSON contains sensitive fitness data and is not encrypted.

> The desktop CLI can be used by scripts or AI agents selected by the user. This is user-directed access to the user's local records, not automatic disclosure by FitOps to an AI service. We request confirmation that the disclosed mobile-to-desktop use is within the approved scenario and guidance on any additional consent or transfer restrictions before implementing Huawei-origin transfer.

The version-1 file exchange is an activity snapshot, not bidirectional synchronization. Revoking access will stop future Huawei reads once the integration handles revocation; it must not be described as deleting exported copies. Local deletion, provider revocation, and deletion of copies at share destinations have distinct effects.

## Requested permissions and historical access

Use Huawei's current console labels and request only permissions needed by the completed mobile screens. The current file-based app does not require Huawei permissions.

| Permission area | Proposed justification |
|---|---|
| Activity record summaries | Activity history, sport, timing, duration, and distance |
| Associated activity samples | Available exercise HR and speed/distance samples for zone breakdowns and supported estimates |
| Historical access | `[OWNER: select one tier and give the actual first-sync/backfill need]` |
| Location/route | Exclude from the initial request unless a working map/route feature actually requires it; current version-1 exchange does not include GPS |
| Sport ability / sport achievement | Exclude from the initial resubmission; FitOps computes its own supported running estimate and does not need these provider metrics for the file-based MVP |
| Writes and broader health data | Exclude: no Huawei writes, sleep, stress, SpO₂, ECG, or blood pressure features in this MVP |

Huawei's [exercise-record guide](https://developer.huawei.com/consumer/en/doc/HMSCore-Guides/introduction-fitness-record-data-0000001131831088/) distinguishes summary, associated-detail, and location scopes. Confirm that the requested scope and account qualification allow the exact sample data needed; do not assume summary approval supplies all streams.

Only one historical dataset permission should be selected. If requesting yearly history, explain the concrete initial-backfill purpose and why a smaller tier is insufficient. Do not select yearly, monthly, and weekly together. The requested tier is not automatically the API request-window size or the local retention period.

## Evidence and truthful self-test status

Before resubmission:

- [ ] Attach the actual released AppGallery listing and application identity.
- [ ] Complete every required field/sheet and replace Huawei's blue example text with truthful FitOps values.
- [ ] Attach real Android UI screenshots and the proposed authorization/data-flow design; label designs as designs.
- [ ] Disclose the optional desktop export and user-directed CLI/agent access.
- [ ] Request one historical dataset and omit unnecessary sport ability/achievement scopes.
- [ ] Verify account type, countries, app scale, dates, and contacts from the owner rather than guessing.

After Huawei grants the applicable development/test authorization:

- [ ] Verify native SDK/plugin compatibility with the chosen Expo/React Native build and production signing identity.
- [ ] Read an authorized activity and the approved available samples on an intended device/account/region.
- [ ] Verify missing-scope, denied consent, expired/revoked access, unavailable-data, and network-error behavior.
- [ ] Verify local persistence, calculated metric provenance, deletion, and the approved export scenario.
- [ ] Collect Huawei self-test evidence and complete any formal/general-availability approval required for the app.

Until these tests are actually performed, enter **Pending — Huawei authorization required for integration testing**, rather than claiming “Pass” or completed live Huawei functionality.

## Clarification message for the existing application

Draft only; not sent:

> We are preparing an independent Android version of FitOps, associated with app ID 117915041 subject to confirmation of the app record/package mapping. It provides local activity-file import, heart-rate calibration/zones, stress approximations, and running VO₂max estimates without a desktop or FitOps cloud account. We will attach AppGallery release evidence when the production app reaches Released status. The proposed read-only Huawei integration would populate the same local mobile features after approval. Users could separately choose to export selected records to their own FitOps Desktop CLI/dashboard, without transferring Huawei credentials; local scripts or agents may access those records at the user's direction. Please confirm whether this disclosed flow is eligible, which individual/enterprise and region restrictions apply to the requested activity-detail samples, and whether our existing app ID can be used for the Android publication. Please also clarify how to obtain test permissions and any formal approval required before general availability.
