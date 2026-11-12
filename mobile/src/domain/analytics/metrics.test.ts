import { calculateMetrics, danielsEstimate } from './metrics';
import { computeZones, validateCalibration } from '../calibration/model';
import type { Activity, Calibration } from '../activities/types';
import references from '../../../contracts/fixtures/metric-reference.json';

export const calibration: Calibration = { sport: 'Run', method: 'lthr', lthr_bpm: 170, max_hr_bpm: null, resting_hr_bpm: null, threshold_pace_seconds_per_km: null, source: 'Field test', calibrated_at: '2026-11-01T00:00:00Z', version: 1 };
function run(hr = 170): Activity {
  return { id: 'test', provider: 'file', provider_account_id: 'local', provider_activity_id: 'test', name: 'Test run', sport: 'Run', start_date: '2026-11-01T08:00:00Z', duration_seconds: 1800, distance_m: 6000, samples: Array.from({ length: 181 }, (_, i) => ({ time_seconds: i * 10, heartrate_bpm: hr, distance_m: i * 6000 / 180, speed_m_per_second: 6000 / 1800 })) };
}
test('LTHR boundaries match desktop and boundary belongs to higher zone', () => {
  expect(computeZones(calibration).map(z => z.lower_bpm)).toEqual([0, 144, 156, 170, 180]);
  const result = calculateMetrics(run(170), calibration);
  expect(result.zones.find(z => z.number === 4)?.seconds).toBe(1800);
  expect(result.tss.value).toBe(50);
});
test('HRR and max-HR zones require valid calibration', () => {
  expect(computeZones({ ...calibration, method: 'hrr', max_hr_bpm: 190, resting_hr_bpm: 50 }).map(z => z.lower_bpm)).toEqual([120,134,148,162,176]);
  expect(computeZones({ ...calibration, method: 'max-hr', max_hr_bpm: 190 }).map(z => z.lower_bpm)).toEqual([95,114,133,152,171]);
  expect(() => validateCalibration({ ...calibration, method: 'hrr' })).toThrow('requires');
  expect(() => validateCalibration({ ...calibration, max_hr_bpm: 160 })).toThrow('below maximum');
  expect(() => validateCalibration({ ...calibration, max_hr_bpm: 190, resting_hr_bpm: 25, lthr_bpm: 180 })).toThrow('overlapping');
});
test('missing calibration, wrong sport, and sparse HR never produce invented stress', () => {
  expect(calculateMetrics(run(), null).tss.value).toBeNull();
  expect(calculateMetrics(run(), { ...calibration, sport: 'Ride' }).tss.value).toBeNull();
  const activity = run(); activity.samples = activity.samples.slice(0, 5);
  expect(calculateMetrics(activity, calibration).tss.value).toBeNull();
  expect(calculateMetrics(activity, calibration).vo2max.value).toBeNull();
});
test('gap breaks continuous VO2max effort and missing time stays unclassified', () => {
  const activity = run(); activity.samples = activity.samples.filter(s => s.time_seconds <= 200 || s.time_seconds >= 1600);
  const result = calculateMetrics(activity, calibration);
  expect(result.hr_coverage_seconds).toBe(400);
  expect(result.unclassified_seconds).toBe(1400);
  expect(result.vo2max.value).toBeNull();
});
test('running estimate follows Daniels model; easy activity does not qualify', () => {
  expect(danielsEstimate(5000,1500)).toBe(38.3);
  expect(calculateMetrics(run(), calibration).vo2max.value).toBe(danielsEstimate(6000,1800));
  expect(calculateMetrics(run(120), calibration).vo2max.value).toBeNull();
  expect(danielsEstimate(10, 0)).toBeNull();
});
test('threshold pace stress is explicit and calibrated; no age or intensity defaults', () => {
  const result = calculateMetrics(run(), { ...calibration, threshold_pace_seconds_per_km: 300 });
  expect(result.tss).toEqual({ value: 50, method: 'pace-stress-v1', reason: null });
});

test.each(references.zone_cases)('shared reference: $name zone boundaries', reference => {
  expect(computeZones(reference.calibration as Calibration).map(z => z.lower_bpm)).toEqual(reference.lower_bpm);
});

test.each(references.daniels_cases)('shared Daniels reference: $distance_m m / $duration_seconds seconds', reference => {
  expect(danielsEstimate(reference.distance_m, reference.duration_seconds)).toBe(reference.expected_ml_per_kg_min);
});

test.each(references.stress_cases)('shared stress reference: $name', reference => {
  const activity = run(reference.heartrate_bpm);
  activity.duration_seconds = reference.duration_seconds;
  activity.distance_m = reference.distance_m;
  activity.samples = Array.from({ length: reference.duration_seconds / 10 + 1 }, (_, i) => ({
    time_seconds: i * 10, heartrate_bpm: reference.heartrate_bpm,
    distance_m: i * 10 * reference.distance_m / reference.duration_seconds,
    speed_m_per_second: reference.distance_m / reference.duration_seconds,
  }));
  const result = calculateMetrics(activity, { ...calibration, threshold_pace_seconds_per_km: reference.threshold_pace_seconds_per_km });
  expect(result.tss.method).toBe(reference.method);
  expect(result.tss.value).toBe(reference.expected_tss);
});

test('all elapsed time is partitioned once, including missing HR and below-zone values', () => {
  const activity = run(80);
  const maxHR = { ...calibration, method: 'max-hr' as const, max_hr_bpm: 190 };
  activity.samples[10].heartrate_bpm = null;
  const result = calculateMetrics(activity, maxHR);
  expect(result.hr_coverage_seconds).toBe(1790);
  expect(result.unclassified_seconds).toBe(1800);
  expect(result.zones.reduce((total,z) => total + z.seconds, 0) + result.unclassified_seconds).toBe(activity.duration_seconds);
});

test('only timestamps covered by HR samples count; final value is not extrapolated', () => {
  const activity = run();
  activity.samples = activity.samples.slice(6, -6);
  const result = calculateMetrics(activity, calibration);
  expect(result.hr_coverage_seconds).toBe(1680);
  expect(result.unclassified_seconds).toBe(120);
});

test('invalid sensor HR cannot qualify a VO2max segment', () => {
  const activity = run();
  activity.samples.forEach((sample,i) => { if (i < 61 || i > 119) sample.heartrate_bpm = 300; });
  expect(calculateMetrics(activity, calibration).vo2max.value).toBeNull();
});

test('max-HR calibration can support VO2max without inventing threshold HR for stress', () => {
  const result = calculateMetrics(run(), { ...calibration, method:'max-hr', lthr_bpm:null, max_hr_bpm:190 });
  expect(result.vo2max.value).not.toBeNull();
  expect(result.tss.value).toBeNull();
});

test('zero duration and a single sensor sample return no estimates or invented coverage', () => {
  const activity = run(); activity.duration_seconds = 0; activity.distance_m = 0; activity.samples = activity.samples.slice(0,1);
  const result = calculateMetrics(activity, calibration);
  expect(result.tss.value).toBeNull(); expect(result.vo2max.value).toBeNull();
  expect(result.hr_coverage_seconds).toBe(0); expect(result.unclassified_seconds).toBe(0);
});

test('distance samples provide speed when no instantaneous speed stream exists', () => {
  const activity = run(); activity.samples.forEach(s => { s.speed_m_per_second = null; });
  expect(calculateMetrics(activity, calibration).vo2max.value).toBe(38.3);
});

test('implausible estimates are rejected rather than clamped to a boundary value', () => {
  expect(danielsEstimate(5000,300)).toBeNull();
  expect(danielsEstimate(1500,2000)).toBeNull();
});
