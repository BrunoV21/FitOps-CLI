import { useState } from "react";
import { Alert } from "react-native";
import { Body, Button, Card, Notice, Screen, Title } from "@/components/ui";
import { useApp } from "@/providers/app-provider";
import { isQaBuild } from "@/infrastructure/runtime";
import { clearExportCache } from "@/infrastructure/transfer/export-cache";
import { buildDemoData } from "./demo-data";

export default function QaScreen() {
  const { activities, mutate, busy } = useApp();
  const [message, setMessage] = useState<string | null>(null);
  if (!isQaBuild)
    return (
      <Screen>
        <Title>QA build only.</Title>
        <Body>Demo controls are unavailable in the production app.</Body>
      </Screen>
    );
  async function reset() {
    const demo = buildDemoData();
    try {
      await mutate(async (repo) => {
        clearExportCache();
        await repo.loadDemoLibrary(demo.activities, demo.calibrations);
      });
      setMessage("Demo library reloaded.");
    } catch {
      /* The application error banner reports failures. */
    }
  }
  return (
    <Screen>
      <Title>QA library.</Title>
      <Card label="Synthetic examples">
        <Body>
          {
            activities.filter(
              (a) => a.activity.provider_account_id === "fitops-demo",
            ).length
          }{" "}
          demo activities loaded
        </Body>
        <Body muted>
          Easy, steady, and threshold runs with sample calibration. No Huawei
          data or personal thresholds.
        </Body>
        <Button
          variant="primary"
          disabled={busy}
          onPress={() =>
            Alert.alert(
              "Reload demo library?",
              "Replace this QA app’s entire local library and calibration with the bundled synthetic examples. Production app data is separate.",
              [
                { text: "Cancel", style: "cancel" },
                { text: "Reload", onPress: () => void reset() },
              ],
            )
          }
        >
          Reload demo library
        </Button>
      </Card>
      {message ? <Notice>{message}</Notice> : null}
      <Notice>
        Keep the demo label in screenshots. These illustrate FitOps features;
        they are not proof of Huawei access or AppGallery publication.
      </Notice>
    </Screen>
  );
}
