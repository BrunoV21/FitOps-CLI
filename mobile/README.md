# FitOps Mobile

Independent Android fitness app in the FitOps repository. Initial scope: calibrated heart-rate zones, activity TSS, and running VO₂max estimates, with local storage and optional desktop export.

- [Architecture and implementation boundaries](architecture.md)
- [UI mockups](mockups/README.md) — open `mockups/index.html` in a browser.
- [Huawei approval and release plan](../docs/providers/huawei/mobile-appgallery-plan.md)
- [Design tokens](src/theme/tokens.json)

This is the architecture and design scaffold. It is not an executable React Native app yet. No dependencies, native project, Huawei credentials, or signing identity have been generated. Mockup values are synthetic and are not calculation reference fixtures.

The mobile package will have its own dependency manifest and lockfile. Existing Python packaging remains unchanged. The reference project is `../BranchBalance` (the actual local directory corresponding to the requested `../branch-balance`). This scaffold adopts its organization; runtime code has not yet been copied.
