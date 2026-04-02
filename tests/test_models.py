"""Tests for DB models."""

from fitops.db.models.activity import Activity
from fitops.db.models.athlete import Athlete


def test_cadence_doubled_for_run():
    assert Activity.get_adjusted_cadence(85.0, "Run") == 170.0


def test_cadence_not_doubled_for_ride():
    assert Activity.get_adjusted_cadence(90.0, "Ride") == 90.0


def test_cadence_none():
    assert Activity.get_adjusted_cadence(None, "Run") is None


def test_athlete_from_strava_data():
    data = {
        "id": 12345,
        "username": "testuser",
        "firstname": "John",
        "lastname": "Doe",
        "city": "London",
        "country": "UK",
        "sex": "M",
        "weight": 70.5,
        "profile": "https://example.com/pic.jpg",
        "premium": True,
        "bikes": [{"id": "b1", "name": "Trek", "distance": 5000, "primary": True}],
        "shoes": [{"id": "s1", "name": "Nike", "distance": 1000, "primary": True}],
    }
    athlete = Athlete.from_strava_data(data)
    assert athlete.strava_id == 12345
    assert athlete.firstname == "John"
    assert len(athlete.bikes) == 1
    assert athlete.get_gear_name("b1") == "Trek"
    assert athlete.get_gear_type("b1") == "bike"
    assert athlete.get_gear_type("s1") == "shoes"


def test_activity_from_strava_data():
    data = {
        "id": 999,
        "name": "Morning Run",
        "sport_type": "Run",
        "start_date": "2026-03-10T07:00:00Z",
        "start_date_local": "2026-03-10T08:00:00Z",
        "distance": 10000.0,
        "moving_time": 3600,
        "elapsed_time": 3650,
        "total_elevation_gain": 100.0,
        "average_speed": 2.78,
        "average_heartrate": 148.0,
        "average_cadence": 87.0,
        "kudos_count": 5,
        "comment_count": 1,
    }
    activity = Activity.from_strava_data(data, athlete_id=12345)
    assert activity.strava_id == 999
    assert activity.distance_m == 10000.0
    assert activity.moving_time_s == 3600
    assert activity.average_cadence == 174.0
