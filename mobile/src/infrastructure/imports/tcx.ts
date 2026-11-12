import { XMLParser, XMLValidator } from 'fast-xml-parser';
import { z } from 'zod';
import type { Activity, Sample, Sport } from '@/domain/activities/types';
import { identity, validateActivity } from '@/domain/activities/schema';

export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;
function array<T>(value: T | T[] | undefined): T[] { return value === undefined ? [] : Array.isArray(value) ? value : [value]; }
function number(value: unknown): number | null {
  if (value === '' || value === undefined || value === null || typeof value === 'boolean') return null;
  const n = Number(value); return Number.isFinite(n) && n >= 0 ? n : null;
}
function timestamp(value: unknown): number {
  if (typeof value !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(value)) throw new Error('TCX timestamps must include a timezone.');
  if (!z.iso.datetime({ offset: true }).safeParse(value).success) throw new Error('Invalid TCX timestamp.');
  const date = Date.parse(value); if (!Number.isFinite(date)) throw new Error('Invalid TCX timestamp.');
  return date;
}

export function parseTcx(text: string): Activity[] {
  if (text.length > MAX_IMPORT_BYTES) throw new Error('File exceeds the 10 MB limit.');
  if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw new Error('TCX files with external entities or document types are not supported.');
  if (XMLValidator.validate(text) !== true) throw new Error('This is not a valid XML activity file.');
  const xml = new XMLParser({ ignoreAttributes: false, removeNSPrefix: true, parseTagValue: false, processEntities: false, maxNestedTags: 64 }).parse(text);
  const records = array<any>(xml?.TrainingCenterDatabase?.Activities?.Activity);
  if (!records.length || records.length > 100) throw new Error('Choose a TCX file containing 1–100 activities.');
  return records.map(record => {
    const start = timestamp(record.Id);
    const laps = array<any>(record.Lap);
    const duration = laps.reduce((total, lap) => total + (number(lap.TotalTimeSeconds) ?? 0), 0);
    const distance = laps.reduce((total, lap) => total + (number(lap.DistanceMeters) ?? 0), 0);
    const sport: Sport = record['@_Sport'] === 'Running' ? 'Run' : record['@_Sport'] === 'Biking' ? 'Ride' : 'Other';
    const samples: Sample[] = [];
    for (const lap of laps) for (const track of array<any>(lap.Track)) for (const point of array<any>(track.Trackpoint)) {
      const time = (timestamp(point.Time) - start) / 1000;
      if (time < 0) throw new Error('A sample occurs before the activity start.');
      const hr = number(point.HeartRateBpm?.Value);
      samples.push({ time_seconds: time, heartrate_bpm: hr !== null && hr >= 25 && hr <= 250 ? hr : null,
        distance_m: number(point.DistanceMeters), speed_m_per_second: number(point.Extensions?.TPX?.Speed) });
      if (samples.length > 100_000) throw new Error('An activity exceeds the 100,000 sample limit.');
    }
    // Lap boundaries may repeat a sample. Keep one deterministic sample for each timestamp.
    const unique = [...new Map(samples.map(s => [s.time_seconds, s])).values()].sort((a,b) => a.time_seconds - b.time_seconds);
    const elapsed = Math.max(duration, unique.at(-1)?.time_seconds ?? 0);
    const origin = { provider: 'file' as const, provider_account_id: 'local', provider_activity_id: `tcx:${sport}:${new Date(start).toISOString()}` };
    return validateActivity({ ...origin, id: identity(origin), name: (typeof record.Notes === 'string' ? record.Notes.trim().slice(0,200) : '') || `${sport === 'Run' ? 'Run' : sport === 'Ride' ? 'Ride' : 'Activity'} · ${new Date(start).toISOString().slice(0,10)}`,
      sport, start_date: new Date(start).toISOString(), duration_seconds: elapsed,
      distance_m: distance || unique.at(-1)?.distance_m || 0, samples: unique });
  });
}
