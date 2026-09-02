from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import AsyncMock

from typer.testing import CliRunner

from fitops.race.course_parser import detect_source, parse_course_file


def _make_kmz_bytes() -> bytes:
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <LineString>
        <coordinates>
          -0.1000,51.5000,12
          -0.1005,51.5005,15
          -0.1010,51.5010,18
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", kml)
    return buf.getvalue()


def test_parse_course_file_supports_kmz(tmp_path):
    kmz_path = tmp_path / "course.kmz"
    kmz_path.write_bytes(_make_kmz_bytes())

    source_type, points = parse_course_file(str(kmz_path))

    assert detect_source(str(kmz_path)) == ("kmz", str(kmz_path))
    assert source_type == "kmz"
    assert len(points) == 3
    assert points[0]["lat"] == 51.5
    assert points[0]["lon"] == -0.1
    assert points[0]["elevation_m"] == 12.0
    assert points[-1]["distance_from_start_m"] > 0.0


def test_race_import_cli_accepts_kmz(tmp_path, monkeypatch):
    from fitops.cli.race import app

    kmz_path = tmp_path / "course.kmz"
    kmz_path.write_bytes(_make_kmz_bytes())

    saved: dict = {}

    async def fake_save_course(**kwargs):
        saved.update(kwargs)
        return {
            "id": 7,
            "name": kwargs["name"],
            "source": kwargs["source"],
            "total_distance_m": kwargs["total_distance_m"],
            "total_elevation_gain_m": kwargs["total_elevation_gain_m"],
        }

    monkeypatch.setattr("fitops.cli.race.init_db", lambda: None)
    monkeypatch.setattr("fitops.cli.race.save_course", fake_save_course)

    result = CliRunner().invoke(
        app,
        ["import", str(kmz_path), "--name", "KMZ Course", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "_meta" in payload
    assert payload["course"]["id"] == 7
    assert saved["source"] == "kmz"
    assert saved["file_format"] == "kmz"
    assert len(saved["course_points"]) == 3


def test_dashboard_race_import_accepts_kmz(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    from fitops.dashboard.server import create_app
    from fitops.db import migrations

    saved: dict = {}

    async def fake_save_course(**kwargs):
        saved.update(kwargs)
        return {"id": 77}

    monkeypatch.setattr(migrations, "create_all_tables", AsyncMock(return_value=None))
    monkeypatch.setattr("fitops.dashboard.routes.race.save_course", fake_save_course)
    monkeypatch.setattr(
        "fitops.dashboard.routes.race.trigger_async", AsyncMock(return_value=None)
    )

    with TestClient(create_app()) as client:
        resp = client.post(
            "/race/import",
            data={"name": "KMZ Course", "source_type": "file"},
            files={
                "file": (
                    "course.kmz",
                    _make_kmz_bytes(),
                    "application/vnd.google-earth.kmz",
                )
            },
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/race/77"
    assert saved["source"] == "kmz"
    assert saved["file_format"] == "kmz"
    assert len(saved["course_points"]) == 3
