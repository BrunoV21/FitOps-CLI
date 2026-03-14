# What's Coming to FitOps

FitOps is built around one idea: your fitness data is yours. The roadmap reflects that — every planned feature either brings more of your data in, or gives you more control over where it lives.

---

## Where we are today

| Phase | Status | What it does |
|-------|--------|-------------|
| Foundation | ✅ Done | Strava sync, activity history, athlete profile, local dashboard |
| Analytics | ✅ Done | Training load (CTL/ATL/TSB), VO2max estimate, zone analysis, trends |
| Workouts | 🔜 Planned | Structured workout plans, compliance scoring, equipment mileage |

---

## What's next

### More data sources — Garmin, Coros, Samsung, Apple, Huawei

Right now FitOps pulls your data from Strava. That works well, but it means you need a Strava account as the middleman — and Strava doesn't always receive data from every device.

The plan is to add **direct integrations with the platforms your devices actually sync to**, so you can pull your data straight from the source:

| Platform | Devices it covers |
|----------|------------------|
| **Garmin Connect** | All Garmin watches and cycling computers |
| **COROS** | COROS Pace, Apex, Vertix, and Dura |
| **Samsung Health** | Galaxy Watch series, Galaxy Ring |
| **Apple Health** | Apple Watch, iPhone fitness tracking |
| **Huawei Health** | Huawei Watch series, Band series |

Once connected, a provider syncs exactly like Strava does today — you run `fitops sync run` and new activities arrive in your local database, regardless of which platform they came from. If you use multiple devices you can connect multiple providers and they all land in the same place.

**For Strava users:** nothing changes. Strava remains a supported provider alongside the others.

**For Apple Health:** because Apple does not yet offer a public REST API for third-party apps, the initial integration will work via an exported Apple Health `.xml` file that you generate from your iPhone. As Apple's API ecosystem evolves, we plan to move to a direct connection.

---

### Cloud backup — Google Drive, OneDrive, Dropbox, Mega

Your FitOps database lives at `~/.fitops/fitops.db`. That's great for privacy and speed, but it means if your machine fails, your data is gone.

The backup feature will let you push a compressed snapshot of your database to the cloud storage provider you already use:

| Provider | Notes |
|----------|-------|
| **Google Drive** | Saves to a `FitOps` folder in your Drive |
| **OneDrive** | Saves to a `FitOps` folder in your OneDrive |
| **Dropbox** | Saves to `/Apps/FitOps/` in your Dropbox |
| **Mega** | Saves to a `FitOps` folder in your Mega account |

**What gets backed up:**
- Your full activity database (`fitops.db`)
- Your sync history
- Your preferences (API credentials are stripped before upload — they never leave your machine)

**How it works:**
- Connect once with `fitops backup configure <provider>`
- Run `fitops backup run` to push a snapshot any time
- Or set a schedule (`fitops backup schedule --cron "0 3 * * *"`) and it happens automatically
- Restore from any previous snapshot with `fitops backup restore`

Backups are versioned with timestamps so you can roll back to any point in time. You control how many snapshots to keep.

---

## The bigger picture

Each of these phases extends the same core promise: **one local database that holds all your training data, accessible to you via the dashboard and to AI agents via the CLI.**

Adding Garmin means a Garmin athlete gets the same analytics and AI coaching capabilities as a Strava athlete. Adding cloud backup means that local-first doesn't have to mean fragile. The interface — dashboard for humans, CLI for agents — stays the same regardless of where the data came from or where the backup lives.

---

## Feedback and priorities

Have a device or cloud provider you'd like to see supported sooner? Open an issue on GitHub and let us know. Priorities for Phase 4 provider order will be shaped by what the community actually uses.
