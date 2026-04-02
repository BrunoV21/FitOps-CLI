from __future__ import annotations

from fitops.workouts.segments import WorkoutSegmentDef


def _parse_pace_str(pace: str) -> float:
    """Convert 'M:SS' pace string to seconds per km."""
    parts = pace.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return float(pace)


def _duration_label(seconds: float) -> str:
    """'30s', '90s', or '2min' label for a duration in seconds."""
    if seconds < 60:
        return f"{int(seconds)}s"
    mins = seconds / 60.0
    if mins == int(mins):
        return f"{int(mins)}min"
    return f"{int(seconds)}s"


def parse_segments_from_json(workout_meta: dict) -> list[WorkoutSegmentDef]:
    """Parse a JSON workout definition into WorkoutSegmentDef list.

    Interval groups are expanded into individual reps + recovery segments so
    that the compliance engine can slice each correctly (no rest-period
    contamination of work-interval averages).

    Expected structure:
      {
        "training": {
          "warmup": {"time_minutes": 13, "heart_rate_range_bpm": {"min": 118, "max": 155}},
          "intervals": [
            {"sets": 4, "run": {"time_seconds": 30, "pace_per_km": {"min": "2:20", "max": "3:30"}},
             "rest": {"time_seconds": 60}},
            ...
          ],
          "cooldown_rest": {"time_minutes": 10, "heart_rate_range_bpm": {"min": 131, "max": 155}}
        }
      }
    """
    training = workout_meta.get("training", workout_meta)
    segments: list[WorkoutSegmentDef] = []
    idx = 0

    # Warmup
    warmup = training.get("warmup")
    if warmup:
        hr = warmup.get("heart_rate_range_bpm", {})
        duration_min = float(warmup.get("time_minutes", 0)) or None
        segments.append(
            WorkoutSegmentDef(
                index=idx,
                name="Warmup",
                step_type="warmup",
                target_zone=None,
                duration_min=duration_min,
                target_hr_min_bpm=float(hr["min"])
                if hr.get("min") is not None
                else None,
                target_hr_max_bpm=float(hr["max"])
                if hr.get("max") is not None
                else None,
                target_focus_type="hr_range" if hr else "none",
            )
        )
        idx += 1

    # Interval groups — expanded into individual reps + recovery segments
    for group in training.get("intervals", []):
        sets = int(group.get("sets", 1))
        run = group.get("run", {})
        rest = group.get("rest", {})

        run_s = float(run.get("time_seconds", 0))
        rest_s = float(rest.get("time_seconds", 0))

        run_pace = run.get("pace_per_km", {})
        pace_min_s = _parse_pace_str(run_pace["min"]) if run_pace.get("min") else None
        pace_max_s = _parse_pace_str(run_pace["max"]) if run_pace.get("max") else None

        rest_pace = rest.get("pace_per_km", {})
        rest_pace_min_s = (
            _parse_pace_str(rest_pace["min"]) if rest_pace.get("min") else None
        )
        rest_pace_max_s = (
            _parse_pace_str(rest_pace["max"]) if rest_pace.get("max") else None
        )

        run_label = _duration_label(run_s)
        rest_label = _duration_label(rest_s)

        for rep in range(1, sets + 1):
            # Work rep
            segments.append(
                WorkoutSegmentDef(
                    index=idx,
                    name=f"{run_label} interval ({rep}/{sets})",
                    step_type="interval",
                    target_zone=None,
                    duration_min=run_s / 60.0 if run_s > 0 else None,
                    target_pace_min_s_per_km=pace_min_s,
                    target_pace_max_s_per_km=pace_max_s,
                    target_focus_type="pace_range"
                    if (pace_min_s or pace_max_s)
                    else "none",
                )
            )
            idx += 1

            # Recovery between reps (always include — last rest still counts toward elapsed time)
            if rest_s > 0:
                segments.append(
                    WorkoutSegmentDef(
                        index=idx,
                        name=f"{rest_label} recovery ({rep}/{sets})",
                        step_type="recovery",
                        target_zone=None,
                        duration_min=rest_s / 60.0,
                        target_pace_min_s_per_km=rest_pace_min_s,
                        target_pace_max_s_per_km=rest_pace_max_s,
                        target_focus_type="pace_range"
                        if (rest_pace_min_s or rest_pace_max_s)
                        else "none",
                    )
                )
                idx += 1

    # Cooldown (key may be "cooldown" or "cooldown_rest")
    cooldown = training.get("cooldown") or training.get("cooldown_rest")
    if cooldown:
        hr = cooldown.get("heart_rate_range_bpm", {})
        duration_min = float(cooldown.get("time_minutes", 0)) or None
        segments.append(
            WorkoutSegmentDef(
                index=idx,
                name="Cooldown",
                step_type="cooldown",
                target_zone=None,
                duration_min=duration_min,
                target_hr_min_bpm=float(hr["min"])
                if hr.get("min") is not None
                else None,
                target_hr_max_bpm=float(hr["max"])
                if hr.get("max") is not None
                else None,
                target_focus_type="hr_range" if hr else "none",
            )
        )

    return segments


def generate_markdown_body(workout_meta: dict, name: str) -> str:
    """Generate a human-readable markdown body from the JSON structure."""
    training = workout_meta.get("training", workout_meta)
    lines: list[str] = [f"# {name}", ""]

    warmup = training.get("warmup")
    if warmup:
        hr = warmup.get("heart_rate_range_bpm", {})
        dur = warmup.get("time_minutes", "?")
        hr_str = f", HR {hr.get('min')}–{hr.get('max')} bpm" if hr else ""
        lines += [f"## Warmup ({dur} min{hr_str})", ""]
        lines += ["Easy running. Keep heart rate within the target range.", ""]

    for group in training.get("intervals", []):
        sets = group.get("sets", 1)
        run = group.get("run", {})
        rest = group.get("rest", {})
        run_s = run.get("time_seconds", 0)
        rest_s = rest.get("time_seconds", 0)
        run_pace = run.get("pace_per_km", {})
        rest_pace = rest.get("pace_per_km", {})

        run_label = _duration_label(run_s)

        pace_str = ""
        if run_pace.get("min") and run_pace.get("max"):
            pace_str = f" @ {run_pace['min']}–{run_pace['max']}/km"

        rest_str = f"{_duration_label(rest_s)} rest"
        if rest_pace.get("min") and rest_pace.get("max"):
            rest_str += f" ({rest_pace['min']}–{rest_pace['max']}/km)"

        heading = f"## {sets}×{run_label} intervals{pace_str} ({rest_str})"
        lines += [heading, ""]
        lines += [
            f"{sets} sets of {run_label} at target pace with {_duration_label(rest_s)} recovery.",
            "",
        ]

    cooldown = training.get("cooldown") or training.get("cooldown_rest")
    if cooldown:
        hr = cooldown.get("heart_rate_range_bpm", {})
        dur = cooldown.get("time_minutes", "?")
        hr_str = f", HR {hr.get('min')}–{hr.get('max')} bpm" if hr else ""
        lines += [f"## Cooldown ({dur} min{hr_str})", ""]
        lines += ["Easy running to bring heart rate down.", ""]

    return "\n".join(lines)
