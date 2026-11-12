# Mobile UI mockups

Open [index.html](index.html) in a browser. No build or dependencies are required. This is a static design prototype, not the React Native application.

The initial proposal covers Overview, Activities, Zones, and Settings. Use the current-section picker in the floating liquid-glass header to change screens; there is no persistent bottom bar. The menu closes after selection, on an outside click, or with Escape. Use the appearance selector for System, Light, or Dark. Only appearance is stored in browser local storage. All activity and athlete values are synthetic illustrations; the prototype does not calculate metrics or connect to Huawei.

Preserve the FitOps black/neon-green identity, monospace type, thin rules, readable mobile spacing, and large touch targets. The full UI now uses a squared glass treatment: 16px corners on the header/menu, 12px on metric cards, and 8px on controls/notes. There are no pill-shaped navigation surfaces. The header uses translucent blur, highlights, and menu animation; content uses more opaque tinted panels with subtle depth. Both themes, reduced-motion support, and opaque navigation fallbacks remain. Native components should follow the semantic [tokens](../src/theme/tokens.json), not embed this HTML.

Next mockup states:

- Activity detail with TSS method and time-in-zone data list.
- Calibration form, input validation, estimated versus confirmed thresholds, and recalculation confirmation.
- Empty library, import selection/review/progress, partial streams, and import failure.
- VO₂max history and insufficient qualifying data.
- Huawei consent, permission denied/revoked, sync failure, and offline access.
- Selected-record export confirmation, deletion, and desktop handoff instructions.

Review at 360px and 430px widths, both themes, large text, keyboard navigation, and reduced motion. Device and screen-reader verification remains necessary once native screens exist.
