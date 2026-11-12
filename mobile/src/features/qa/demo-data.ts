import type { Activity, Calibration, Sample } from "@/domain/activities/types";
import { identity, validateActivity } from "@/domain/activities/schema";
import { validateCalibration } from "@/domain/calibration/model";

/** Deterministic, synthetic QA data. This is never a Huawei data source. */
export function buildDemoData(): {
  activities: Activity[];
  calibrations: Calibration[];
} {
  const calibration: Calibration = {
    sport: "Run",
    method: "lthr",
    max_hr_bpm: 190,
    resting_hr_bpm: 50,
    lthr_bpm: 170,
    threshold_pace_seconds_per_km: 300,
    source: "Synthetic QA calibration — not personal thresholds",
    calibrated_at: "2026-11-01T00:00:00.000Z",
    version: 1,
  };
  validateCalibration(calibration);

  const definitions = [
    {
      key: "easy-run-v1",
      name: "Demo · Easy run (synthetic)",
      start: "2026-11-01T08:00:00.000Z",
      seconds: 1200,
      speed: 2.5,
      heartRate: () => 135,
    },
    {
      key: "steady-run-v1",
      name: "Demo · Steady run (synthetic)",
      start: "2026-11-03T08:00:00.000Z",
      seconds: 1800,
      speed: 3.2,
      heartRate: () => 148,
    },
    {
      key: "threshold-run-v1",
      name: "Demo · Threshold run (synthetic)",
      start: "2026-11-05T08:00:00.000Z",
      seconds: 2400,
      speed: 3.7,
      heartRate: (seconds: number) =>
        seconds < 300 ? 142 : seconds < 600 ? 160 : seconds < 2100 ? 172 : 184,
    },
  ];

  const activities = definitions.map((definition) => {
    const origin = {
      provider: "file" as const,
      provider_account_id: "fitops-demo",
      provider_activity_id: definition.key,
    };
    const samples: Sample[] = Array.from(
      { length: definition.seconds / 10 + 1 },
      (_, i) => ({
        time_seconds: i * 10,
        heartrate_bpm: definition.heartRate(i * 10),
        distance_m: Math.round(i * 10 * definition.speed * 1000) / 1000,
        speed_m_per_second: definition.speed,
      }),
    );
    return validateActivity({
      ...origin,
      id: identity(origin),
      name: definition.name,
      sport: "Run",
      start_date: definition.start,
      duration_seconds: definition.seconds,
      distance_m: definition.seconds * definition.speed,
      samples,
    });
  });

  return { activities, calibrations: [calibration] };
}
