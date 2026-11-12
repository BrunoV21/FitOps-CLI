import { DatabaseSync } from "node:sqlite";
import { ActivityRepository, type Database } from "./repository";
import type { Activity, Calibration } from "@/domain/activities/types";
import { buildDemoData } from "@/features/qa/demo-data";

function database(): Database {
  const sqlite = new DatabaseSync(":memory:");
  const db: Database = {
    async execAsync(sql) {
      sqlite.exec(sql);
    },
    async runAsync(sql, ...values) {
      return sqlite.prepare(sql).run(...values);
    },
    async getAllAsync<T>(sql: string, ...values: (string | number | null)[]) {
      return sqlite.prepare(sql).all(...values) as T[];
    },
    async getFirstAsync<T>(sql: string, ...values: (string | number | null)[]) {
      return (sqlite.prepare(sql).get(...values) as T) ?? null;
    },
    async withExclusiveTransactionAsync(task) {
      sqlite.exec("BEGIN");
      try {
        await task(db);
        sqlite.exec("COMMIT");
      } catch (e) {
        sqlite.exec("ROLLBACK");
        throw e;
      }
    },
  };
  return db;
}
const c: Calibration = {
  sport: "Run",
  method: "lthr",
  lthr_bpm: 170,
  max_hr_bpm: null,
  resting_hr_bpm: null,
  threshold_pace_seconds_per_km: 300,
  source: "Test",
  calibrated_at: "2026-11-01T00:00:00Z",
  version: 1,
};
const activity: Activity = {
  id: "untrusted",
  provider: "file",
  provider_account_id: "local",
  provider_activity_id: "one",
  name: "Run",
  sport: "Run",
  start_date: "2026-11-01T08:00:00Z",
  duration_seconds: 1800,
  distance_m: 6000,
  samples: [],
};
test("real SQLite import deduplicates, persists metrics and recalibrates retrospectively", async () => {
  const r = new ActivityRepository(database());
  await r.initialize();
  expect(await r.importActivities([activity])).toEqual({
    created: 1,
    updated: 0,
  });
  expect((await r.snapshot()).activities[0].metrics.tss.value).toBeNull();
  await r.saveCalibration(c);
  expect((await r.snapshot()).activities[0].metrics.tss.value).toBe(50);
  expect(await r.importActivities([activity])).toEqual({
    created: 0,
    updated: 1,
  });
  await r.saveCalibration({ ...c, threshold_pace_seconds_per_km: 240 });
  const state = await r.snapshot();
  expect(state.activities).toHaveLength(1);
  expect(state.activities[0].metrics.tss.value).toBe(32);
  expect(state.activities[0].metrics.calibration_version).toBe(2);
  await r.clearCalibration("Run");
  expect((await r.snapshot()).activities[0].metrics.tss.value).toBeNull();
  await r.deleteActivity(state.activities[0].activity.id);
  expect((await r.snapshot()).activities).toEqual([]);
});
test("invalid import/calibration leaves existing records unchanged", async () => {
  const r = new ActivityRepository(database());
  await r.initialize();
  await r.importActivities([activity]);
  await expect(
    r.importActivities([{ ...activity, duration_seconds: -2 }]),
  ).rejects.toThrow();
  await expect(r.saveCalibration({ ...c, lthr_bpm: null })).rejects.toThrow();
  expect((await r.snapshot()).activities).toHaveLength(1);
  await r.deleteAll();
  expect((await r.snapshot()).activities).toHaveLength(0);
});

test("QA data preloads once, erasure stays empty, and explicit reload is deterministic", async () => {
  const r = new ActivityRepository(database());
  await r.initialize();
  const demo = buildDemoData();
  await r.loadDemoLibrary(demo.activities, demo.calibrations, true);
  const initial = await r.snapshot();
  expect(initial.activities).toHaveLength(3);
  expect(initial.activities[0].metrics.vo2max.value).toBe(43.6);
  await r.deleteAll();
  await r.loadDemoLibrary(demo.activities, demo.calibrations, true);
  expect((await r.snapshot()).activities).toHaveLength(0);
  await r.loadDemoLibrary(demo.activities, demo.calibrations);
  expect(await r.snapshot()).toEqual(initial);
  await expect(
    r.loadDemoLibrary([activity], demo.calibrations),
  ).rejects.toThrow("synthetic");
  expect(await r.snapshot()).toEqual(initial);
});
