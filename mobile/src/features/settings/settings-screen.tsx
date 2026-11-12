import { useState } from "react";
import { Alert } from "react-native";
import {
  Body,
  Button,
  Card,
  Choice,
  Disclosure,
  Notice,
  Screen,
  Title,
} from "@/components/ui";
import { useTheme, type ThemePreference } from "@/providers/theme-provider";
import { useApp } from "@/providers/app-provider";
import { clearExportCache } from "@/infrastructure/transfer/export-cache";

export default function SettingsScreen() {
  const { preference, setPreference } = useTheme(),
    { mutate, busy } = useApp(),
    [error, setError] = useState<string | null>(null);
  const change = (next: ThemePreference) => {
    setError(null);
    void setPreference(next).catch(() =>
      setError("Could not save appearance preference."),
    );
  };
  return (
    <Screen>
      <Title>Make it yours.</Title>
      <Body muted>Appearance and your data.</Body>
      <Card label="Appearance">
        <Choice
          label="Color mode"
          value={preference}
          onChange={change}
          options={[
            { value: "system", label: "System" },
            { value: "dark", label: "Dark" },
            { value: "light", label: "Light" },
          ]}
        />
        {error ? <Notice>{error}</Notice> : null}
      </Card>
      <Card label="Huawei Health">
        <Body>Permission approval is pending.</Body>
        <Disclosure label="Connection details">
          <Body muted size={13}>
            Huawei sync is not available yet. Use TCX imports now. No Huawei
            credentials are requested or stored.
          </Body>
        </Disclosure>
      </Card>
      <Card label="Your data">
        <Body>Stored on this phone. Shared only when you export.</Body>
        <Disclosure label="Privacy and data handling">
          <Body muted size={13}>
            Activity records, samples, calibration, and metrics use local SQLite
            storage. Appearance is stored separately. There is no cloud account,
            advertising, tracking, or automatic upload. Android backup is disabled.
          </Body>
          <Body muted size={13}>
            Imports use files you select. Exports use Android’s share sheet and
            contain unencrypted fitness data. Another app may upload that data
            according to its settings; copies remain until deleted there.
          </Body>
          <Body muted size={13}>
            Delete individual activities in their details or calibration in Zones.
            Uninstalling removes local app data, but not original files or exports.
          </Body>
        </Disclosure>
      </Card>
      <Card label="Clear local library">
        <Body>
          Delete all activities, samples, and calibrations.
        </Body>
        <Button
          variant="danger"
          disabled={busy}
          onPress={() =>
            Alert.alert(
              "Erase the local library?",
              "This cannot be undone. Exported copies and original files are unaffected.",
              [
                { text: "Cancel", style: "cancel" },
                {
                  text: "Erase library",
                  style: "destructive",
                  onPress: () =>
                      void mutate(async (repo) => { clearExportCache(); await repo.deleteAll(); }).catch(() => {}),
                },
              ],
            )
          }
        >
          Erase local activities and calibration
        </Button>
      </Card>
      <Body muted size={13}>FitOps 0.1.0 · Android</Body>
    </Screen>
  );
}
