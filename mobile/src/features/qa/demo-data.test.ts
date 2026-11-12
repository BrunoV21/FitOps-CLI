import { buildDemoData } from "./demo-data";
import { calculateMetrics } from "@/domain/analytics/metrics";
import { activitySchema, identity } from "@/domain/activities/schema";
import { computeZones, validateCalibration } from "@/domain/calibration/model";

test("demo data is deterministic and every record is clearly synthetic, never Huawei", () => {
  const first = buildDemoData();
  expect(first).toEqual(buildDemoData());
  expect(first.activities).toHaveLength(3);
  expect(new Set(first.activities.map((a) => a.id)).size).toBe(3);
  for (const activity of first.activities) {
    expect(activitySchema.safeParse(activity).success).toBe(true);
    expect(activity.name).toMatch(/^Demo · .*\(synthetic\)$/);
    expect(activity.provider).toBe("file");
    expect(activity.provider_account_id).toBe("fitops-demo");
    expect(activity.id).toBe(identity(activity));
    expect(activity.samples.at(-1)?.time_seconds).toBe(
      activity.duration_seconds,
    );
  }
});

test("demo calibration is explicitly synthetic and provides valid, ordered zones", () => {
  const [calibration] = buildDemoData().calibrations;
  expect(() => validateCalibration(calibration)).not.toThrow();
  expect(calibration.source).toBe(
    "Synthetic QA calibration — not personal thresholds",
  );
  expect(computeZones(calibration).map((z) => z.lower_bpm)).toEqual([
    0, 144, 150, 170, 180,
  ]);
});

test("demo activities exercise different stress values and qualified versus unqualified running estimates", () => {
  const { activities, calibrations } = buildDemoData();
  const results = activities.map((activity) =>
    calculateMetrics(activity, calibrations[0]),
  );
  expect(results.map((result) => result.tss.value)).toEqual([
    18.75, 46.08, 82.14,
  ]);
  expect(results.map((result) => result.vo2max.value)).toEqual([
    null,
    null,
    43.6,
  ]);
  expect(results[2].zones.map((z) => z.seconds)).toEqual([
    300, 0, 300, 1500, 300,
  ]);
  expect(results[2].hr_coverage_seconds).toBe(2400);
  expect(results[2].unclassified_seconds).toBe(0);
  expect(results[2].average_heartrate_bpm).toBe(168.3);
});

test("every demo reset gets fresh arrays and objects rather than a mutated singleton", () => {
  const first = buildDemoData();
  first.activities[0].samples[0].heartrate_bpm = null;
  first.activities[0].name = "Changed";
  first.calibrations[0].lthr_bpm = 160;
  const reset = buildDemoData();
  expect(reset.activities[0].samples[0].heartrate_bpm).toBe(135);
  expect(reset.activities[0].name).toBe("Demo · Easy run (synthetic)");
  expect(reset.calibrations[0].lthr_bpm).toBe(170);
});
