from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MetaBlock(BaseModel):
    tool: str = "fitops"
    version: str = "0.1.0"
    generated_at: str
    total_count: int | None = None
    filters_applied: dict | None = None


class ActivitySummaryOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    strava_activity_id: int
    name: str
    sport_type: str
    start_date_local: str | None = None
    start_date_utc: str | None = None


class SyncResultOutput(BaseModel):
    sync_type: str
    activities_created: int
    activities_updated: int
    pages_fetched: int
    duration_s: float
    synced_at: str
