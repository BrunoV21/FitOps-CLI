# Provider Integrations

FitOps started as a Strava-backed local analytics tool. New activity sources must be added as providers, not as one-off branches in CLI or dashboard code.

Provider planning docs:

| Provider | Status | Notes |
|----------|--------|-------|
| Strava | Shipped | Current default provider and canonical compatibility target. |
| Huawei Health | Planned | Design notes live in [`huawei/`](./huawei/). API access and real payload fixtures are still required before implementation. |

Provider work must preserve the project rules in `AGENTS.md`: shared logic first, CLI and dashboard parity, docs, and tests. Runtime support is not complete until the provider can be selected, synced, queried through CLI JSON, and viewed in the dashboard from the same local database.

