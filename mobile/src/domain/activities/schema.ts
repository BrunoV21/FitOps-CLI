import { z } from 'zod';
import type { Activity } from './types';

export const sampleSchema = z.object({
  time_seconds: z.number().finite().min(0).max(7 * 86400),
  heartrate_bpm: z.number().min(25).max(250).nullable(),
  distance_m: z.number().min(0).max(2_000_000).nullable(),
  speed_m_per_second: z.number().min(0).max(100).nullable(),
}).strict();
export const activitySchema = z.object({
  id: z.string().min(1).max(1024), provider: z.enum(['file','huawei']), provider_account_id: z.string().min(1).max(200),
  provider_activity_id: z.string().min(1).max(512), name: z.string().trim().min(1).max(200),
  sport: z.enum(['Run','Ride','Walk','Other']), start_date: z.iso.datetime({ offset: true }),
  duration_seconds: z.number().positive().max(7 * 86400), distance_m: z.number().min(0).max(2_000_000),
  samples: z.array(sampleSchema).max(100_000),
}).strict().superRefine((a, ctx) => {
  for (let i = 0; i < a.samples.length; i++) {
    if (a.samples[i].time_seconds > a.duration_seconds || (i > 0 && a.samples[i].time_seconds <= a.samples[i - 1].time_seconds)) {
      ctx.addIssue({ code: 'custom', message: 'Samples must be chronological, unique, and within the activity duration.', path: ['samples',i] });
      break;
    }
  }
});
export function identity(a: Pick<Activity, 'provider' | 'provider_account_id' | 'provider_activity_id'>): string {
  return JSON.stringify([a.provider, a.provider_account_id, a.provider_activity_id]);
}
export function validateActivity(input: unknown): Activity {
  const a = activitySchema.parse(input);
  return { ...a, id: identity(a) };
}
