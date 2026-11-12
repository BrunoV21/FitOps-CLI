import { z } from "zod";
import {
  activitySchema,
  identity,
  validateActivity,
} from "@/domain/activities/schema";
import type { Activity } from "@/domain/activities/types";

const exchangeSchema = z
  .object({
    format: z.literal("fitops.activities"),
    version: z.literal(1),
    exported_at: z.iso.datetime({ offset: true }),
    activities: z.array(activitySchema).min(1).max(100),
  })
  .strict()
  .superRefine((value, ctx) => {
    const keys = value.activities.map(identity);
    if (new Set(keys).size !== keys.length) {
      ctx.addIssue({
        code: "custom",
        message: "The export contains repeated source identities.",
        path: ["activities"],
      });
    }
  });

export function exportActivities(
  activities: Activity[],
  now = new Date(),
): string {
  return JSON.stringify(
    exchangeSchema.parse({
      format: "fitops.activities",
      version: 1,
      exported_at: now.toISOString(),
      activities,
    }),
    null,
    2,
  );
}
export function parseExchange(text: string): Activity[] {
  const data = exchangeSchema.parse(JSON.parse(text));
  return data.activities.map(validateActivity);
}
