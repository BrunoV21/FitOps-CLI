from __future__ import annotations

from pathlib import Path

import markdown as md_lib

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

_HERE = Path(__file__).parent


def create_app() -> FastAPI:
    from fitops.dashboard.routes import activities, analytics, api, notes, overview, profile, workouts

    app = FastAPI(title="FitOps Dashboard", docs_url=None, redoc_url=None)

    app.mount(
        "/static",
        StaticFiles(directory=str(_HERE / "static")),
        name="static",
    )

    templates = Jinja2Templates(directory=str(_HERE / "templates"))

    # --- Sport SVG icons (inline, currentColor, 16×16 viewBox 0 0 24 24) ---
    _S = 'width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:middle;flex-shrink:0;"'

    # Run — classic side-view runner: head, forward-leaning torso, opposing arms, mid-stride legs
    _RUN = f'<svg {_S}><circle cx="14.5" cy="4" r="2"/><path d="M14 6L11 14"/><path d="M13 9L17 6.5"/><path d="M12 9L8 12"/><path d="M11 14L7.5 18L6 22"/><path d="M11 14L14 18.5L18 22"/></svg>'
    # Trail run — run + mountain
    _TRAIL = f'<svg {_S}><circle cx="12" cy="4" r="1.8"/><path d="M8 21l3-8 3 3 3.5-6"/><path d="M3 21l5-9 4 4 4-8 5 13"/></svg>'
    # Walk
    _WALK = f'<svg {_S}><circle cx="12" cy="4" r="1.8"/><path d="M9 21l2-6 2 3 2-4"/><path d="M7 10l2-2h5l1 4"/></svg>'
    # Hike — person + mountain peak
    _HIKE = f'<svg {_S}><circle cx="12" cy="4" r="1.8"/><path d="M9 9l-3 12h12"/><path d="M4 19l8-14 8 14"/></svg>'
    # Ride / VirtualRide — bicycle
    _BIKE = f'<svg {_S}><circle cx="6" cy="15" r="4"/><circle cx="18" cy="15" r="4"/><path d="M6 15l4-8h4l3 8"/><path d="M10 7h4"/></svg>'
    # EBike — bicycle + lightning bolt
    _EBIKE = f'<svg {_S}><circle cx="6" cy="15" r="4"/><circle cx="18" cy="15" r="4"/><path d="M6 15l4-8h4l3 8"/><path d="M13 3l-2 4h3l-2 4"/></svg>'
    # Swim — wave
    _SWIM = f'<svg {_S}><path d="M2 12c1.5-2 3-2 4.5 0s3 2 4.5 0 3-2 4.5 0 3 2 4.5 0"/><path d="M2 17c1.5-2 3-2 4.5 0s3 2 4.5 0 3-2 4.5 0 3 2 4.5 0"/><path d="M12 3v5"/><circle cx="12" cy="2.5" r="1"/></svg>'
    # Rowing — oar strokes
    _ROW = f'<svg {_S}><path d="M5 19l14-14"/><path d="M3 12l4-4 4 4-4 4z"/><path d="M17 6l3 3-3 3"/></svg>'
    # Yoga — person in tree pose (simplified)
    _YOGA = f'<svg {_S}><circle cx="12" cy="4" r="1.8"/><path d="M12 6v6"/><path d="M9 10l3 2 3-2"/><path d="M12 12l-3 6"/><path d="M12 12l3 6"/></svg>'
    # WeightTraining / Workout / Crossfit — dumbbell
    _DUMBBELL = f'<svg {_S}><path d="M6 8v8"/><path d="M18 8v8"/><path d="M6 12h12"/><rect x="3" y="7" width="3" height="10" rx="0"/><rect x="18" y="7" width="3" height="10" rx="0"/></svg>'
    # Soccer — circle + cross hatching (simplified ball)
    _SOCCER = f'<svg {_S}><circle cx="12" cy="12" r="9"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="M6.3 6.3l2.8 2.8M14.9 14.9l2.8 2.8M17.7 6.3l-2.8 2.8M9.1 14.9l-2.8 2.8"/></svg>'
    # Tennis — racket
    _TENNIS = f'<svg {_S}><ellipse cx="10" cy="9" rx="6" ry="7"/><path d="M14 14l5 5"/><path d="M7 9h6M10 6v6"/></svg>'
    # Golf — flag on pin
    _GOLF = f'<svg {_S}><path d="M12 21V6"/><path d="M12 6l8 4-8 4V6z"/><path d="M6 21h12"/></svg>'
    # AlpineSki / NordicSki — skis crossed
    _SKI = f'<svg {_S}><path d="M5 19l14-14"/><path d="M19 19L5 5"/><circle cx="12" cy="4" r="1.8"/><path d="M10 8l2 2 2-2"/></svg>'
    # StandUpPaddling / Surfing — person on wave
    _SURF = f'<svg {_S}><circle cx="12" cy="4" r="1.8"/><path d="M9 8l3 4 3-4"/><path d="M2 16c2-3 4-3 6 0s4 3 6 0 4-3 6 0"/></svg>'
    # Default — activity lightning bolt
    _DEFAULT = f'<svg {_S}><path d="M13 2L4 14h8l-1 8 9-12h-8l1-8z"/></svg>'

    _SPORT_ICONS: dict[str, Markup] = {
        "Run":              Markup(_RUN),
        "VirtualRun":       Markup(_RUN),
        "TrailRun":         Markup(_TRAIL),
        "Walk":             Markup(_WALK),
        "Hike":             Markup(_HIKE),
        "Ride":             Markup(_BIKE),
        "VirtualRide":      Markup(_BIKE),
        "EBikeRide":        Markup(_EBIKE),
        "Swim":             Markup(_SWIM),
        "Rowing":           Markup(_ROW),
        "Yoga":             Markup(_YOGA),
        "WeightTraining":   Markup(_DUMBBELL),
        "Workout":          Markup(_DUMBBELL),
        "Crossfit":         Markup(_DUMBBELL),
        "Soccer":           Markup(_SOCCER),
        "Tennis":           Markup(_TENNIS),
        "Golf":             Markup(_GOLF),
        "AlpineSki":        Markup(_SKI),
        "NordicSki":        Markup(_SKI),
        "StandUpPaddling":  Markup(_SURF),
        "Surfing":          Markup(_SURF),
    }

    def sport_icon(sport: str) -> Markup:
        return _SPORT_ICONS.get(sport, Markup(_DEFAULT))

    templates.env.globals["sport_icon"] = sport_icon
    templates.env.filters["render_md"] = lambda text: Markup(
        md_lib.markdown(text or "", extensions=["nl2br", "fenced_code"])
    )

    # Register all routers (each route module returns its router after
    # binding the shared templates instance)
    app.include_router(api.register())
    app.include_router(overview.register(templates))
    app.include_router(activities.register(templates))
    app.include_router(analytics.register(templates))
    app.include_router(profile.register(templates))
    app.include_router(workouts.register(templates))
    app.include_router(notes.register(templates))

    return app
