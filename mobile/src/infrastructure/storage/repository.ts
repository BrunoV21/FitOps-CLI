import { calculateMetrics } from "@/domain/analytics/metrics";
import { validateCalibration } from "@/domain/calibration/model";
import { validateActivity } from "@/domain/activities/schema";
import type {
  Activity,
  Calibration,
  SavedActivity,
  Sport,
} from "@/domain/activities/types";

type Value = string | number | null;
export interface Database {
  execAsync(sql: string): Promise<void>;
  runAsync(sql: string, ...values: Value[]): Promise<unknown>;
  getAllAsync<T>(sql: string, ...values: Value[]): Promise<T[]>;
  getFirstAsync<T>(sql: string, ...values: Value[]): Promise<T | null>;
  withExclusiveTransactionAsync(
    task: (db: Database) => Promise<void>,
  ): Promise<void>;
}
export type Snapshot = {
  activities: SavedActivity[];
  calibrations: Calibration[];
};

export class ActivityRepository {
  constructor(private db: Database) {}
  // Called once by application initialization; never from a feature read path.
  async initialize(): Promise<void> {
    await this.db.execAsync(`PRAGMA journal_mode = WAL;
      CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS calibration (sport TEXT PRIMARY KEY, data TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS activity (id TEXT PRIMARY KEY, start_date TEXT NOT NULL, sport TEXT NOT NULL, data TEXT NOT NULL, metrics TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS activity_date ON activity(start_date DESC);
      INSERT OR IGNORE INTO schema_version(version) VALUES (1);`);
  }
  async snapshot(): Promise<Snapshot> {
    const activities = await this.db.getAllAsync<{
      data: string;
      metrics: string;
    }>("SELECT data, metrics FROM activity ORDER BY start_date DESC, id");
    const calibrations = await this.db.getAllAsync<{ data: string }>(
      "SELECT data FROM calibration ORDER BY sport",
    );
    return {
      activities: activities.map((row) => ({
        activity: JSON.parse(row.data),
        metrics: JSON.parse(row.metrics),
      })),
      calibrations: calibrations.map((row) => JSON.parse(row.data)),
    };
  }
  async importActivities(
    input: Activity[],
  ): Promise<{ created: number; updated: number }> {
    const activities = input.map(validateActivity);
    if (activities.length > 100)
      throw new Error("Import up to 100 activities at once.");
    let created = 0,
      updated = 0;
    await this.db.withExclusiveTransactionAsync(async (db) => {
      const calibrations = await db.getAllAsync<{ data: string }>(
        "SELECT data FROM calibration",
      );
      const profiles: Calibration[] = calibrations.map((row) =>
        JSON.parse(row.data),
      );
      for (const activity of activities) {
        const found = await db.getFirstAsync<{ id: string }>(
          "SELECT id FROM activity WHERE id = ?",
          activity.id,
        );
        const metrics = calculateMetrics(
          activity,
          profiles.find((c) => c.sport === activity.sport) ?? null,
        );
        await db.runAsync(
          "INSERT INTO activity(id,start_date,sport,data,metrics) VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET start_date=excluded.start_date,sport=excluded.sport,data=excluded.data,metrics=excluded.metrics",
          activity.id,
          activity.start_date,
          activity.sport,
          JSON.stringify(activity),
          JSON.stringify(metrics),
        );
        if (found) updated++;
        else created++;
      }
    });
    return { created, updated };
  }
  async saveCalibration(input: Calibration): Promise<void> {
    validateCalibration(input);
    await this.db.withExclusiveTransactionAsync(async (db) => {
      const previous = await db.getFirstAsync<{ data: string }>(
        "SELECT data FROM calibration WHERE sport = ?",
        input.sport,
      );
      const next = {
        ...input,
        version: previous
          ? (JSON.parse(previous.data) as Calibration).version + 1
          : 1,
      };
      const rows = await db.getAllAsync<{ id: string; data: string }>(
        "SELECT id,data FROM activity WHERE sport = ?",
        input.sport,
      );
      await db.runAsync(
        "INSERT INTO calibration(sport,data) VALUES (?,?) ON CONFLICT(sport) DO UPDATE SET data=excluded.data",
        next.sport,
        JSON.stringify(next),
      );
      for (const row of rows) {
        const metrics = calculateMetrics(JSON.parse(row.data), next);
        await db.runAsync(
          "UPDATE activity SET metrics = ? WHERE id = ?",
          JSON.stringify(metrics),
          row.id,
        );
      }
    });
  }
  async deleteActivity(id: string): Promise<void> {
    await this.db.runAsync("DELETE FROM activity WHERE id = ?", id);
  }
  async clearCalibration(sport: Sport): Promise<void> {
    await this.db.withExclusiveTransactionAsync(async (db) => {
      await db.runAsync("DELETE FROM calibration WHERE sport = ?", sport);
      const rows = await db.getAllAsync<{ id: string; data: string }>(
        "SELECT id,data FROM activity WHERE sport = ?",
        sport,
      );
      for (const row of rows)
        await db.runAsync(
          "UPDATE activity SET metrics = ? WHERE id = ?",
          JSON.stringify(calculateMetrics(JSON.parse(row.data), null)),
          row.id,
        );
    });
  }
  async deleteAll(): Promise<void> {
    await this.db.withExclusiveTransactionAsync(async (db) => {
      await db.runAsync("DELETE FROM activity");
      await db.runAsync("DELETE FROM calibration");
    });
  }

  private async writeDemoLibrary(
    db: Database,
    activities: Activity[],
    calibrations: Calibration[],
  ): Promise<void> {
    await db.runAsync("DELETE FROM activity");
    await db.runAsync("DELETE FROM calibration");
    for (const c of calibrations)
      await db.runAsync(
        "INSERT INTO calibration(sport,data) VALUES (?,?)",
        c.sport,
        JSON.stringify(c),
      );
    for (const activity of activities) {
      const metrics = calculateMetrics(
        activity,
        calibrations.find((c) => c.sport === activity.sport) ?? null,
      );
      await db.runAsync(
        "INSERT INTO activity(id,start_date,sport,data,metrics) VALUES (?,?,?,?,?)",
        activity.id,
        activity.start_date,
        activity.sport,
        JSON.stringify(activity),
        JSON.stringify(metrics),
      );
    }
    await db.runAsync(
      "INSERT INTO app_state(key,value) VALUES ('demo_seeded','1') ON CONFLICT(key) DO UPDATE SET value='1'",
    );
  }

  async loadDemoLibrary(
    input: Activity[],
    calibrations: Calibration[],
    firstLaunchOnly = false,
  ): Promise<void> {
    const activities = input.map(validateActivity);
    calibrations.forEach(validateCalibration);
    if (
      !activities.length ||
      activities.length > 100 ||
      activities.some(
        (a) => a.provider !== "file" || a.provider_account_id !== "fitops-demo",
      )
    )
      throw new Error(
        "The QA library must contain only labelled synthetic activities.",
      );
    if (
      new Set(activities.map((a) => a.id)).size !== activities.length ||
      new Set(calibrations.map((c) => c.sport)).size !== calibrations.length
    )
      throw new Error("The QA library contains duplicate identities.");
    await this.db.withExclusiveTransactionAsync(async (db) => {
      if (firstLaunchOnly) {
        const seeded = await db.getFirstAsync<{ value: string }>(
          "SELECT value FROM app_state WHERE key='demo_seeded'",
        );
        if (seeded) return;
        const existing = await db.getFirstAsync<{ count: number }>(
          "SELECT COUNT(*) AS count FROM activity",
        );
        const existingCalibration = await db.getFirstAsync<{ count: number }>(
          "SELECT COUNT(*) AS count FROM calibration",
        );
        if (existing?.count || existingCalibration?.count) {
          await db.runAsync(
            "INSERT OR IGNORE INTO app_state(key,value) VALUES ('demo_seeded','1')",
          );
          return;
        }
      }
      await this.writeDemoLibrary(db, activities, calibrations);
    });
  }
}

let startup: Promise<ActivityRepository> | undefined;
export function openRepository(qaMode = false): Promise<ActivityRepository> {
  startup ??= (async () => {
    const { openDatabaseAsync } = await import("expo-sqlite");
    const db = await openDatabaseAsync(
      qaMode ? "fitops-mobile-qa.db" : "fitops-mobile.db",
    );
    const repository = new ActivityRepository(db as Database);
    await repository.initialize();
    return repository;
  })().catch((error) => {
    startup = undefined;
    throw error;
  });
  return startup;
}
