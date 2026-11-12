import { Directory, File, Paths } from "expo-file-system";

export function exportDirectory(): Directory {
  const directory = new Directory(Paths.cache, "fitops-exports");
  if (!directory.exists)
    directory.create({ idempotent: true, intermediates: true });
  return directory;
}
export function cleanupExportCache(now = Date.now()): void {
  const directory = exportDirectory();
  for (const item of directory.list()) {
    if (
      item instanceof File &&
      item.modificationTime !== null &&
      now - item.modificationTime > 24 * 3600 * 1000
    )
      item.delete();
  }
}
export function clearExportCache(): void {
  const directory = new Directory(Paths.cache, "fitops-exports");
  if (directory.exists) directory.delete();
}
