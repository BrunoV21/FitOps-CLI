import * as Sharing from "expo-sharing";
import { shareActivities } from "./share-export";
import {
  cleanupExportCache,
  clearExportCache,
} from "@/infrastructure/transfer/export-cache";
import type { Activity } from "@/domain/activities/types";

const mockFiles = new Map<string, { text: string; modified: number }>();
const mockFolders = new Set<string>();
jest.mock("expo-sharing", () => ({
  isAvailableAsync: jest.fn(),
  shareAsync: jest.fn(),
}));
jest.mock("expo-file-system", () => {
  class File {
    uri: string;
    constructor(parent: { uri: string } | string, name = "") {
      this.uri =
        `${typeof parent === "string" ? parent : parent.uri}/${name}`.replace(
          /\/$/,
          "",
        );
    }
    get exists() {
      return mockFiles.has(this.uri);
    }
    get modificationTime() {
      return mockFiles.get(this.uri)?.modified ?? null;
    }
    create() {
      mockFiles.set(this.uri, { text: "", modified: Date.now() });
    }
    write(text: string) {
      mockFiles.set(this.uri, { text, modified: Date.now() });
    }
    delete() {
      mockFiles.delete(this.uri);
    }
  }
  class Directory {
    uri: string;
    constructor(parent: { uri: string }, name: string) {
      this.uri = `${parent.uri}/${name}`;
    }
    get exists() {
      return mockFolders.has(this.uri);
    }
    create() {
      mockFolders.add(this.uri);
    }
    list() {
      return [...mockFiles.keys()]
        .filter((key) => key.startsWith(this.uri + "/"))
        .map((key) => new File(key));
    }
    delete() {
      for (const key of mockFiles.keys())
        if (key.startsWith(this.uri + "/")) mockFiles.delete(key);
      mockFolders.delete(this.uri);
    }
  }
  return { File, Directory, Paths: { cache: { uri: "file:///cache" } } };
});
const activity: Activity = {
  id: "one",
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
beforeEach(() => {
  mockFiles.clear();
  mockFolders.clear();
  jest.mocked(Sharing.isAvailableAsync).mockResolvedValue(true);
  jest.mocked(Sharing.shareAsync).mockResolvedValue(undefined);
});
test("shared export remains readable after chooser returns, then expires on later cleanup", async () => {
  await shareActivities([activity]);
  const [uri, entry] = [...mockFiles.entries()][0];
  expect(Sharing.shareAsync).toHaveBeenCalledWith(
    uri,
    expect.objectContaining({ mimeType: "application/json" }),
  );
  expect(JSON.parse(entry.text).activities).toEqual([activity]);
  cleanupExportCache(entry.modified + 23 * 3600 * 1000);
  expect(mockFiles.size).toBe(1);
  cleanupExportCache(entry.modified + 25 * 3600 * 1000);
  expect(mockFiles.size).toBe(0);
});
test("library erase clears app-owned temporary exports and a sharing failure cleans current file", async () => {
  await shareActivities([activity]);
  clearExportCache();
  expect(mockFiles.size).toBe(0);
  jest
    .mocked(Sharing.shareAsync)
    .mockRejectedValueOnce(new Error("No recipient"));
  await expect(shareActivities([activity])).rejects.toThrow("No recipient");
  expect(mockFiles.size).toBe(0);
});
