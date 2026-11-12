import * as DocumentPicker from "expo-document-picker";
import { File, Paths } from "expo-file-system";
import { parseTcx, MAX_IMPORT_BYTES } from "@/infrastructure/imports/tcx";
import { parseExchange } from "@/infrastructure/transfer/exchange";
import type { Activity } from "@/domain/activities/types";

export async function pickActivities(): Promise<{
  name: string;
  activities: Activity[];
} | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: "*/*",
    copyToCacheDirectory: true,
    multiple: false,
  });
  if (result.canceled) return null;
  const asset = result.assets[0],
    file = new File(asset.uri);
  try {
    if ((asset.size ?? file.size ?? 0) > MAX_IMPORT_BYTES)
      throw new Error("Choose a file smaller than 10 MB.");
    const text = await file.text();
    if (text.length > MAX_IMPORT_BYTES)
      throw new Error("Choose a file smaller than 10 MB.");
    const name = asset.name.toLowerCase();
    if (!name.endsWith(".tcx") && !name.endsWith(".json"))
      throw new Error(
        "Choose a .tcx activity file or a FitOps .json export. FIT and GPX imports are not supported in this version.",
      );
    return {
      name: asset.name,
      activities: name.endsWith(".tcx") ? parseTcx(text) : parseExchange(text),
    };
  } finally {
    if (asset.uri.startsWith(Paths.cache.uri) && file.exists) file.delete();
  }
}
