from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).parent


def create_app() -> FastAPI:
    from fitops.dashboard.routes import activities, analytics, overview, workouts

    app = FastAPI(title="FitOps Dashboard", docs_url=None, redoc_url=None)

    app.mount(
        "/static",
        StaticFiles(directory=str(_HERE / "static")),
        name="static",
    )

    templates = Jinja2Templates(directory=str(_HERE / "templates"))

    # --- Template globals ---
    _SPORT_ICONS = {
        "Run": "🏃", "TrailRun": "🏔️", "Walk": "🚶", "Hike": "🥾",
        "Ride": "🚴", "VirtualRide": "🚴", "EBikeRide": "⚡",
        "Swim": "🏊", "Rowing": "🚣", "Yoga": "🧘",
        "WeightTraining": "🏋️", "Workout": "💪", "Crossfit": "💪",
        "Soccer": "⚽", "Tennis": "🎾", "Golf": "⛳",
        "AlpineSki": "⛷️", "NordicSki": "🎿",
        "StandUpPaddling": "🏄", "Surfing": "🏄",
        "VirtualRun": "🏃",
    }

    def sport_icon(sport: str) -> str:
        return _SPORT_ICONS.get(sport, "🏅")

    templates.env.globals["sport_icon"] = sport_icon

    # Register all routers (each route module returns its router after
    # binding the shared templates instance)
    app.include_router(overview.register(templates))
    app.include_router(activities.register(templates))
    app.include_router(analytics.register(templates))
    app.include_router(workouts.register(templates))

    return app
