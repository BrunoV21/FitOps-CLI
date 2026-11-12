import type { Calibration, Zone } from '../activities/types';

export function validateCalibration(value: Calibration): void {
  if (!['Run', 'Ride', 'Walk', 'Other'].includes(value.sport)) throw new Error('Choose a supported calibration sport.');
  if (!['lthr', 'hrr', 'max-hr'].includes(value.method)) throw new Error('Choose LTHR, heart-rate reserve, or maximum-HR zones.');
  const { max_hr_bpm: max, resting_hr_bpm: rest, lthr_bpm: lthr } = value;
  for (const [name, number] of [['Maximum HR', max], ['Resting HR', rest], ['Threshold HR', lthr]] as const) {
    if (number !== null && (!Number.isInteger(number) || number < 25 || number > 250)) throw new Error(`${name} must be a whole number between 25 and 250.`);
  }
  if (max !== null && rest !== null && rest >= max) throw new Error('Resting HR must be below maximum HR.');
  if (lthr !== null && max !== null && lthr >= max) throw new Error('Threshold HR must be below maximum HR.');
  if (lthr !== null && rest !== null && lthr <= rest) throw new Error('Threshold HR must be above resting HR.');
  if (value.method === 'lthr' && lthr === null) throw new Error('Enter your threshold HR for the LTHR method.');
  if (value.method === 'max-hr' && max === null) throw new Error('Enter your maximum HR for this method.');
  if (value.method === 'hrr' && (max === null || rest === null)) throw new Error('Heart-rate reserve requires maximum and resting HR.');
  const pace = value.threshold_pace_seconds_per_km;
  if (pace !== null && (!Number.isFinite(pace) || pace < 120 || pace > 1200)) throw new Error('Threshold pace must be between 120 and 1200 seconds per kilometre.');
  if (!value.source.trim() || value.source.length > 200) throw new Error('Describe the source of your calibration (up to 200 characters).');
  if (!Number.isFinite(Date.parse(value.calibrated_at))) throw new Error('Invalid calibration date.');
  if (!Number.isInteger(value.version) || value.version < 1) throw new Error('Invalid calibration version.');
  const bounds = zoneBounds(value);
  if (bounds.some((b, i) => i > 0 && b <= bounds[i - 1])) throw new Error('These inputs produce overlapping zones. Review your thresholds or choose another method.');
}

// Mirrors desktop zone boundaries. Upper bounds are exclusive; a boundary belongs to the next zone.
function zoneBounds(c: Calibration): number[] {
  if (c.method === 'lthr') {
    const lthr = c.lthr_bpm!;
    const lt1 = c.resting_hr_bpm !== null && c.max_hr_bpm !== null
      ? Math.trunc(c.resting_hr_bpm + .72 * (c.max_hr_bpm - c.resting_hr_bpm)) : Math.trunc(lthr * .92);
    return [0, Math.trunc(lthr * .85), lt1, lthr, Math.trunc(lthr * 1.06)];
  }
  const rest = c.method === 'hrr' ? c.resting_hr_bpm! : 0;
  const reserve = c.max_hr_bpm! - rest;
  return [.5, .6, .7, .8, .9].map(ratio => Math.trunc(rest + ratio * reserve));
}

export function computeZones(c: Calibration): Zone[] {
  validateCalibration(c);
  const bounds = zoneBounds(c);
  return ['Recovery', 'Aerobic', 'Tempo', 'Threshold', 'High intensity'].map((name, i) => ({
    number: i + 1, name, lower_bpm: bounds[i], upper_bpm: bounds[i + 1] ?? null,
  }));
}
