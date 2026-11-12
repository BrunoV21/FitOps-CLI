import { File } from "expo-file-system";
import * as Sharing from "expo-sharing";
import type { Activity } from "@/domain/activities/types";
import { exportActivities } from "@/infrastructure/transfer/exchange";
import {
  cleanupExportCache,
  exportDirectory,
} from "@/infrastructure/transfer/export-cache";

export async function shareActivities(activities: Activity[]): Promise<void> {
  if (!(await Sharing.isAvailableAsync()))
    throw new Error("File sharing is unavailable on this device.");
  if (!activities.length)
    throw new Error("Select at least one activity to export.");
  const data = exportActivities(activities);
  if (data.length > 10 * 1024 * 1024)
    throw new Error("This export exceeds 10 MB. Select fewer activities.");
  cleanupExportCache();
  const file = new File(exportDirectory(), `fitops-export-${Date.now()}.json`);
  try {
    file.create();
    file.write(data);
    await Sharing.shareAsync(file.uri, {
      mimeType: "application/json",
      dialogTitle: "Export selected FitOps activities",
      UTI: "public.json",
    });
  } catch (error) {
    if (file.exists) file.delete();
    throw error;
  }
  // Android's chooser can return before the recipient reads the URI. Keep the
  // temporary file available; the next startup/export expires it after 24 hours.
}
