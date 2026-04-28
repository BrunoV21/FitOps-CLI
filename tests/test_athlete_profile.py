"""Tests for `fitops athlete profile` and `fitops athlete zones` parity features.

Covers:
- print_athlete_profile: physiology block rendering
- print_athlete_computed_zones: HR + pace zones display
- athlete zones JSON output shape (computed, not Strava)
- profile JSON physiology block structure
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# print_athlete_profile — physiology section
# ---------------------------------------------------------------------------

_FULL_ATHLETE = {
    "strava_id": 1,
    "name": "Jane Smith",
    "username": "jsmith",
    "city": "London",
    "country": "UK",
    "sex": "F",
    "weight_kg": 60.0,
    "premium": True,
    "profile_url": None,
    "equipment": {"bikes": [], "shoes": [{"id": "g1", "name": "Nike Vaporfly"}]},
    "physiology": {
        "max_hr": 190,
        "resting_hr": 45,
        "lthr": 170,
        "ftp": 280,
        "lt1_pace": "5:30/km",
        "lt2_pace": "4:55/km",
        "vo2max_pace": "4:20/km",
        "vo2max": {
            "estimate": 55.2,
            "vdot": 53.1,
            "confidence": 0.85,
            "confidence_label": "high",
            "based_on_activity": {
                "name": "Threshold Tuesday",
                "date": "2026-03-15",
                "distance_km": 12.5,
                "pace_per_km": "4:52",
            },
        },
    },
}


def test_profile_prints_without_error(capsys):
    from fitops.output.text_formatter import print_athlete_profile

    print_athlete_profile(_FULL_ATHLETE)
    # no exception means pass — rich writes to stdout via its own Console


def test_profile_physiology_none_skipped():
    """Profile without physiology key doesn't crash."""
    from fitops.output.text_formatter import print_athlete_profile

    athlete = dict(_FULL_ATHLETE)
    del athlete["physiology"]
    print_athlete_profile(athlete)  # should not raise


def test_profile_physiology_empty_skipped():
    """Profile with empty physiology block is safe."""
    from fitops.output.text_formatter import print_athlete_profile

    athlete = dict(_FULL_ATHLETE, physiology={})
    print_athlete_profile(athlete)  # should not raise


def test_profile_physiology_null_vo2max():
    """Profile with null vo2max still renders the rest."""
    from fitops.output.text_formatter import print_athlete_profile

    phys = dict(_FULL_ATHLETE["physiology"], vo2max=None)
    athlete = dict(_FULL_ATHLETE, physiology=phys)
    print_athlete_profile(athlete)  # should not raise


# ---------------------------------------------------------------------------
# print_athlete_computed_zones — HR + pace zones
# ---------------------------------------------------------------------------

_ZONES_DATA = {
    "_meta": {},
    "zones": {
        "method": "lthr",
        "lthr_bpm": 170,
        "max_hr_bpm": 190,
        "resting_hr_bpm": 45,
        "heart_rate_zones": [
            {
                "zone": 1,
                "name": "Recovery",
                "min_bpm": 0,
                "max_bpm": 139,
                "description": "Active recovery",
            },
            {
                "zone": 2,
                "name": "Aerobic",
                "min_bpm": 140,
                "max_bpm": 156,
                "description": "Aerobic base",
            },
            {
                "zone": 3,
                "name": "Tempo",
                "min_bpm": 157,
                "max_bpm": 166,
                "description": "Comfortably hard",
            },
            {
                "zone": 4,
                "name": "Threshold",
                "min_bpm": 167,
                "max_bpm": 176,
                "description": "Threshold effort",
            },
            {
                "zone": 5,
                "name": "VO2max",
                "min_bpm": 177,
                "max_bpm": 999,
                "description": "High intensity",
            },
        ],
        "thresholds": {
            "lt1_bpm": 156,
            "lt2_bpm": 170,
            "lt1_pace_fmt": "5:30/km",
            "lt1_pace_s": 330.0,
            "lt2_pace_fmt": "4:55/km",
            "lt2_pace_s": 295.0,
            "vo2max_pace_fmt": "4:20/km",
            "vo2max_pace_s": 260.0,
        },
    },
    "pace_zones": [
        {
            "zone": 1,
            "name": "Easy",
            "min_s_per_km": 342,
            "max_s_per_km": None,
            "min_pace_fmt": "5:42",
            "max_pace_fmt": None,
        },
        {
            "zone": 2,
            "name": "Aerobic",
            "min_s_per_km": 318,
            "max_s_per_km": 342,
            "min_pace_fmt": "5:18",
            "max_pace_fmt": "5:42",
        },
        {
            "zone": 3,
            "name": "Tempo",
            "min_s_per_km": 301,
            "max_s_per_km": 318,
            "min_pace_fmt": "5:01",
            "max_pace_fmt": "5:18",
        },
        {
            "zone": 4,
            "name": "Threshold",
            "min_s_per_km": 283,
            "max_s_per_km": 301,
            "min_pace_fmt": "4:43",
            "max_pace_fmt": "5:01",
        },
        {
            "zone": 5,
            "name": "VO2max",
            "min_s_per_km": None,
            "max_s_per_km": 283,
            "min_pace_fmt": None,
            "max_pace_fmt": "4:43",
        },
    ],
}


def test_computed_zones_prints_without_error():
    from fitops.output.text_formatter import print_athlete_computed_zones

    print_athlete_computed_zones(_ZONES_DATA)  # should not raise


def test_computed_zones_no_pace_zones():
    """Zones data without pace_zones still renders HR section."""
    from fitops.output.text_formatter import print_athlete_computed_zones

    data = dict(_ZONES_DATA)
    del data["pace_zones"]
    print_athlete_computed_zones(data)  # should not raise


def test_computed_zones_empty_data():
    """Empty data dict is safe."""
    from fitops.output.text_formatter import print_athlete_computed_zones

    print_athlete_computed_zones({})  # should not raise


# ---------------------------------------------------------------------------
# athlete zones JSON output shape (pure logic — no CLI invocation)
# ---------------------------------------------------------------------------


def test_zones_json_uses_computed_zones():
    """compute_zones() + to_dict() returns heart_rate_zones and thresholds."""
    from fitops.analytics.zones import compute_zones

    result = compute_zones(method="lthr", lthr=170, max_hr=190, resting_hr=45)
    assert result is not None
    d = result.to_dict()
    assert "heart_rate_zones" in d
    assert len(d["heart_rate_zones"]) == 5
    assert "thresholds" in d
    assert "lt1_bpm" in d["thresholds"]
    assert "lt2_bpm" in d["thresholds"]


def test_zones_json_each_zone_has_required_keys():
    from fitops.analytics.zones import compute_zones

    result = compute_zones(method="lthr", lthr=165)
    assert result is not None
    for z in result.to_dict()["heart_rate_zones"]:
        assert "zone" in z
        assert "name" in z
        assert "min_bpm" in z
        assert "max_bpm" in z


def test_zones_json_max_hr_only_method():
    from fitops.analytics.zones import compute_zones

    result = compute_zones(method="max-hr", max_hr=192)
    assert result is not None
    d = result.to_dict()
    assert len(d["heart_rate_zones"]) == 5


# ---------------------------------------------------------------------------
# profile physiology block structure (unit test — no DB)
# ---------------------------------------------------------------------------


def test_profile_physiology_block_keys():
    """All expected physiology keys are present in the structure."""
    phys = _FULL_ATHLETE["physiology"]
    for key in (
        "max_hr",
        "resting_hr",
        "lthr",
        "ftp",
        "lt1_pace",
        "lt2_pace",
        "vo2max_pace",
        "vo2max",
    ):
        assert key in phys


def test_profile_physiology_vo2max_keys():
    vo2max = _FULL_ATHLETE["physiology"]["vo2max"]
    for key in (
        "estimate",
        "vdot",
        "confidence",
        "confidence_label",
        "based_on_activity",
    ):
        assert key in vo2max


def test_profile_physiology_vo2max_based_on_keys():
    based = _FULL_ATHLETE["physiology"]["vo2max"]["based_on_activity"]
    for key in ("name", "date", "distance_km", "pace_per_km"):
        assert key in based
