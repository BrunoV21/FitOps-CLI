import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { useApp } from "@/providers/app-provider";
import { ThemeProvider } from "@/providers/theme-provider";
import OverviewScreen from "@/features/overview/overview-screen";
import ActivitiesScreen from "@/features/activities/activities-screen";
import ActivityScreen from "@/features/activities/activity-screen";
import ZonesScreen from "@/features/zones/zones-screen";
import SettingsScreen from "@/features/settings/settings-screen";
import { pickActivities } from "@/features/imports/file-import";
import { calculateMetrics } from "@/domain/analytics/metrics";
import type { Activity, Calibration } from "@/domain/activities/types";

jest.mock("expo-router", () => ({
  useRouter: jest.fn(),
  useLocalSearchParams: jest.fn(),
}));
jest.mock("@/providers/app-provider", () => ({ useApp: jest.fn() }));
jest.mock("@/features/imports/file-import", () => ({
  pickActivities: jest.fn(),
}));
jest.mock("@/features/exports/share-export", () => ({
  shareActivities: jest.fn(),
}));
jest.mock("@/infrastructure/transfer/export-cache", () => ({ clearExportCache: jest.fn() }));
const activity: Activity = {
  id: "one",
  provider: "file",
  provider_account_id: "local",
  provider_activity_id: "one",
  name: "Morning run",
  sport: "Run",
  start_date: "2026-11-01T08:00:00Z",
  duration_seconds: 1800,
  distance_m: 6000,
  samples: [],
};
const base = {
  activities: [],
  calibrations: [],
  loading: false,
  busy: false,
  error: null,
  mutate: jest.fn(),
  retry: jest.fn(),
  clearError: jest.fn(),
};
beforeEach(() => {
  jest.clearAllMocks();
  jest
    .mocked(useRouter)
    .mockReturnValue({ push: jest.fn(), replace: jest.fn() } as never);
  jest.mocked(useLocalSearchParams).mockReturnValue({ id: "one" });
  jest.mocked(useApp).mockReturnValue({ ...base } as never);
});

test("overview starts with actionable empty states and no fabricated values", async () => {
  const screen = await render(
    <ThemeProvider>
      <OverviewScreen />
    </ThemeProvider>,
  );
  expect(
    screen.getByRole("button", { name: "Import an activity" }),
  ).toBeTruthy();
  expect(screen.getByText("No activities imported yet.")).toBeTruthy();
  expect(screen.getByText(/Set running LTHR/)).toBeTruthy();
});
test("calibration rejects missing thresholds and saves entered inputs explicitly", async () => {
  const save = jest.fn().mockResolvedValue(undefined);
  const mutate = jest.fn(async (action) => action({ saveCalibration: save }));
  jest.mocked(useApp).mockReturnValue({ ...base, mutate } as never);
  const screen = await render(
    <ThemeProvider>
      <ZonesScreen />
    </ThemeProvider>,
  );
  await fireEvent.press(
    screen.getByRole("button", { name: "Save and recalculate" }),
  );
  expect(
    screen.getByText("Enter your threshold HR for the LTHR method."),
  ).toBeTruthy();
  expect(mutate).not.toHaveBeenCalled();
  await fireEvent.changeText(
    screen.getByLabelText("Threshold HR (LTHR) · beats/min"),
    "170",
  );
  await fireEvent.changeText(
    screen.getByLabelText("Calibration source"),
    "Field test",
  );
  await fireEvent.press(
    screen.getByRole("button", { name: "Save and recalculate" }),
  );
  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(
      expect.objectContaining({
        sport: "Run",
        method: "lthr",
        lthr_bpm: 170,
        max_hr_bpm: null,
        source: "Field test",
      }),
    ),
  );
});
test("import requires explicit review/save and handles cancellation", async () => {
  const importActivities = jest
    .fn()
    .mockResolvedValue({ created: 1, updated: 0 });
  const mutate = jest.fn(async (action) => action({ importActivities }));
  jest.mocked(useApp).mockReturnValue({ ...base, mutate } as never);
  jest
    .mocked(pickActivities)
    .mockResolvedValue({ name: "run.tcx", activities: [activity] });
  const screen = await render(
    <ThemeProvider>
      <ActivitiesScreen />
    </ThemeProvider>,
  );
  await fireEvent.press(
    screen.getByRole("button", { name: "Import TCX / FitOps file" }),
  );
  expect(screen.getByText("REVIEW IMPORT")).toBeTruthy();
  expect(mutate).not.toHaveBeenCalled();
  await fireEvent.press(
    screen.getByRole("button", { name: "Save to this phone" }),
  );
  await waitFor(() =>
    expect(importActivities).toHaveBeenCalledWith([activity]),
  );
  expect(screen.getByText(/1 imported, 0 updated/)).toBeTruthy();
  jest.mocked(pickActivities).mockResolvedValue(null);
  await fireEvent.press(
    screen.getByRole("button", { name: "Import TCX / FitOps file" }),
  );
  expect(screen.queryByText("REVIEW IMPORT")).toBeNull();
});
test("activity detail reports missing data and deletion requires confirmation", async () => {
  const remove = jest.fn().mockResolvedValue(undefined),
    mutate = jest.fn(async (action) => action({ deleteActivity: remove }));
  jest
    .mocked(useApp)
    .mockReturnValue({
      ...base,
      activities: [{ activity, metrics: calculateMetrics(activity, null) }],
      mutate,
    } as never);
  const dialog = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  const screen = await render(
    <ThemeProvider>
      <ActivityScreen />
    </ThemeProvider>,
  );
  expect(screen.getByText(/Set a sport-specific LTHR/)).toBeTruthy();
  expect(screen.queryByText(/Elapsed hours × intensity/)).toBeNull();
  const explanation = screen.getByRole("button", { name: "How stress is estimated" });
  expect(explanation.props.accessibilityState.expanded).toBe(false);
  await fireEvent.press(explanation);
  expect(screen.getByText(/Elapsed hours × intensity/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "How stress is estimated" }).props.accessibilityState.expanded).toBe(true);
  await fireEvent.press(
    screen.getByRole("button", { name: "Delete activity" }),
  );
  expect(remove).not.toHaveBeenCalled();
  const button = dialog.mock.calls[0][2]?.find((b) => b.text === "Delete");
  await act(async () => {
    button?.onPress?.();
  });
  expect(remove).toHaveBeenCalledWith("one");
  dialog.mockRestore();
});
test("settings explains Huawei availability and erasure needs explicit confirmation", async () => {
  const dialog = jest.spyOn(Alert, "alert").mockImplementation(() => {});
  const screen = await render(
    <ThemeProvider>
      <SettingsScreen />
    </ThemeProvider>,
  );
  expect(screen.getByText("Permission approval is pending.")).toBeTruthy();
  expect(screen.queryByText(/Activity records, samples, calibration, and metrics use local SQLite/)).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Privacy and data handling" }));
  expect(screen.getByText(/Activity records, samples, calibration, and metrics use local SQLite/)).toBeTruthy();
  await fireEvent.press(
    screen.getByRole("button", {
      name: "Erase local activities and calibration",
    }),
  );
  expect(base.mutate).not.toHaveBeenCalled();
  expect(dialog).toHaveBeenCalledWith(
    "Erase the local library?",
    expect.any(String),
    expect.any(Array),
  );
  dialog.mockRestore();
});

test("saved zones keep calibration editing and optional inputs collapsed", async () => {
  const calibration: Calibration = {
    sport: "Run", method: "lthr", lthr_bpm: 170, max_hr_bpm: null,
    resting_hr_bpm: null, threshold_pace_seconds_per_km: null,
    source: "Field test", calibrated_at: "2026-11-01T00:00:00Z", version: 1,
  };
  jest.mocked(useApp).mockReturnValue({ ...base, calibrations: [calibration] } as never);
  const screen = await render(<ThemeProvider><ZonesScreen /></ThemeProvider>);
  expect(screen.getByText("Z1 · Recovery")).toBeTruthy();
  expect(screen.queryByLabelText("Threshold HR (LTHR) · beats/min")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Edit calibration" }));
  expect(screen.getByLabelText("Threshold HR (LTHR) · beats/min").props.value).toBe("170");
  expect(screen.getByText("Saving recalculates all activities for this sport on this phone.")).toBeTruthy();
  expect(screen.queryByLabelText("Maximum HR · beats/min")).toBeNull();
  await fireEvent.press(screen.getByRole("button", { name: "Optional thresholds" }));
  expect(screen.getByLabelText("Maximum HR · beats/min")).toBeTruthy();
});
