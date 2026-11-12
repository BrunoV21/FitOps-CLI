export type Sport = 'Run' | 'Ride' | 'Walk' | 'Other';
export type ZoneMethod = 'lthr' | 'hrr' | 'max-hr';
export type Calibration = {
  sport: Sport;
  method: ZoneMethod;
  max_hr_bpm: number | null;
  resting_hr_bpm: number | null;
  lthr_bpm: number | null;
  threshold_pace_seconds_per_km: number | null;
  source: string;
  calibrated_at: string;
  version: number;
};
export type Sample = {
  time_seconds: number;
  heartrate_bpm: number | null;
  distance_m: number | null;
  speed_m_per_second: number | null;
};
export type Activity = {
  id: string;
  provider: 'file' | 'huawei';
  provider_account_id: string;
  provider_activity_id: string;
  name: string;
  sport: Sport;
  start_date: string;
  duration_seconds: number;
  distance_m: number;
  samples: Sample[];
};
export type Zone = { number: number; name: string; lower_bpm: number; upper_bpm: number | null };
export type Metric = { value: number | null; reason: string | null; method: string };
export type Metrics = {
  calculation_version: string;
  calibration_version: number | null;
  tss: Metric;
  vo2max: Metric;
  zones: { number: number; seconds: number }[];
  hr_coverage_seconds: number;
  unclassified_seconds: number;
  average_heartrate_bpm: number | null;
};
export type SavedActivity = { activity: Activity; metrics: Metrics };
