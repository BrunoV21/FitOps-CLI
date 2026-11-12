import type { Activity, Calibration, Metric, Metrics } from '../activities/types';
import { computeZones } from '../calibration/model';

export const CALCULATION_VERSION = 'mobile-1';
const round = (n: number, places = 1) => Math.round((n + Number.EPSILON) * 10 ** places) / 10 ** places;
const missing = (reason: string, method: string): Metric => ({ value: null, reason, method });

// Desktop Daniels/VDOT pace model. This is a performance proxy, not a laboratory VO₂max measurement.
export function danielsEstimate(distance_m: number, duration_seconds: number): number | null {
  if (duration_seconds <= 0 || distance_m < 1500) return null;
  const v = distance_m / duration_seconds * 60;
  const minutes = duration_seconds / 60;
  const fraction = minutes <= 3 ? 1 : minutes <= 10 ? .98 : minutes <= 20 ? .96 : minutes <= 40 ? .94 : minutes <= 60 ? .92 : minutes <= 120 ? .88 : .84;
  const result = (-4.6 + .182258 * v + .000104 * v * v) / fraction;
  // Unlike desktop's clipping, reject implausible estimates rather than displaying a boundary as a measurement.
  return Number.isFinite(result) && result >= 20 && result <= 90 ? round(result) : null;
}

export function calculateMetrics(activity: Activity, calibration: Calibration | null): Metrics {
  const c = calibration?.sport === activity.sport ? calibration : null;
  const definitions = c ? computeZones(c) : [];
  const zones = definitions.map(z => ({ number: z.number, seconds: 0 }));
  let hrSeconds = 0, hrTotal = 0, unknown = 0;
  let segmentSeconds = 0, segmentDistance = 0;
  let qualifyingSeconds = 0, qualifyingDistance = 0;
  const effortFloor = c?.lthr_bpm ? c.lthr_bpm * .9 : c?.max_hr_bpm ? c.max_hr_bpm * .8 : null;
  const flush = () => {
    if (segmentSeconds >= 600) { qualifyingSeconds += segmentSeconds; qualifyingDistance += segmentDistance; }
    segmentSeconds = 0; segmentDistance = 0;
  };
  const samples = activity.samples;
  for (let i = 0; i < samples.length - 1; i++) {
    const current = samples[i], next = samples[i + 1];
    const dt = next.time_seconds - current.time_seconds;
    // Never extend sensor values over pauses/gaps or beyond the activity interval.
    if (!Number.isFinite(dt) || dt <= 0 || dt > 30 || current.time_seconds < 0 || next.time_seconds > activity.duration_seconds) { flush(); continue; }
    const hr = current.heartrate_bpm;
    const validHr = hr !== null && Number.isFinite(hr) && hr >= 25 && hr <= 250;
    if (validHr) {
      hrSeconds += dt; hrTotal += hr * dt;
      const zone = definitions.find(z => hr >= z.lower_bpm && (z.upper_bpm === null || hr < z.upper_bpm));
      if (zone) zones[zone.number - 1].seconds += dt; else unknown += dt;
    }
    const distanceDelta = current.distance_m !== null && next.distance_m !== null ? next.distance_m - current.distance_m : null;
    const speed = current.speed_m_per_second ?? (distanceDelta !== null && distanceDelta >= 0 ? distanceDelta / dt : null);
    if (validHr && effortFloor !== null && hr >= effortFloor && speed !== null && Number.isFinite(speed) && speed >= .5 && speed <= 12) {
      segmentSeconds += dt; segmentDistance += speed * dt;
    } else flush();
  }
  flush();
  const averageHr = hrSeconds > 0 ? hrTotal / hrSeconds : null;
  let tss = missing('Set a sport-specific LTHR or running threshold pace to estimate stress.', 'unavailable');
  if (activity.duration_seconds <= 0) tss = missing('Activity duration is missing.', 'unavailable');
  else if (c && activity.sport === 'Run' && c.threshold_pace_seconds_per_km && activity.distance_m > 0) {
    const intensity = (activity.distance_m / activity.duration_seconds) / (1000 / c.threshold_pace_seconds_per_km);
    tss = intensity > 2 ? missing('Pace is outside the supported estimation range. Review the activity.', 'pace-stress-v1') : {
      value: round(activity.duration_seconds / 3600 * intensity ** 2 * 100, 2), reason: null, method: 'pace-stress-v1',
    };
  } else if (c?.lthr_bpm && averageHr !== null) {
    // Require substantial measured coverage; do not extrapolate sparse HR over a whole session.
    tss = hrSeconds / activity.duration_seconds < .8
      ? missing('At least 80% timestamped HR coverage is required for HR-based stress.', 'hr-stress-v1')
      : { value: round(activity.duration_seconds / 3600 * (averageHr / c.lthr_bpm) ** 2 * 100, 2), reason: null, method: 'hr-stress-v1' };
  }
  let vo2max = missing('Only running activities are supported.', 'daniels-streams-v1');
  if (activity.sport === 'Run') {
    if (!effortFloor) vo2max = missing('Set running LTHR or maximum HR first.', 'daniels-streams-v1');
    else if (qualifyingSeconds < 600 || qualifyingDistance < 1500 || averageHr === null || averageHr < effortFloor) vo2max = missing('Needs at least 10 continuous minutes and 1.5 km near threshold with usable HR and speed samples.', 'daniels-streams-v1');
    else {
      const estimate = danielsEstimate(qualifyingDistance, qualifyingSeconds);
      vo2max = estimate === null ? missing('Qualifying data is outside the supported estimation range.', 'daniels-streams-v1') : { value: estimate, reason: null, method: 'daniels-streams-v1' };
    }
  }
  return {
    calculation_version: CALCULATION_VERSION, calibration_version: c?.version ?? null, tss, vo2max, zones,
    hr_coverage_seconds: round(hrSeconds), unclassified_seconds: round(activity.duration_seconds - hrSeconds + unknown),
    average_heartrate_bpm: averageHr === null ? null : round(averageHr),
  };
}
