import { useState } from "react";
import { Alert, Pressable, View } from "react-native";
import { useRouter } from "expo-router";
import {
  Body,
  Button,
  Card,
  Choice,
  Disclosure,
  Notice,
  Row,
  Screen,
  Title,
} from "@/components/ui";
import { useApp } from "@/providers/app-provider";
import { useTheme } from "@/providers/theme-provider";
import type { Activity, Sport } from "@/domain/activities/types";
import { pickActivities } from "../imports/file-import";
import { shareActivities } from "../exports/share-export";
import { dateLabel, duration } from "../format";

export default function ActivitiesScreen() {
  const { activities, mutate, busy } = useApp(),
    { colors } = useTheme(),
    router = useRouter();
  const [draft, setDraft] = useState<{
      name: string;
      activities: Activity[];
    } | null>(null),
    [working, setWorking] = useState(false),
    [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState<string | null>(null),
    [selected, setSelected] = useState<string[]>([]),
    [sport, setSport] = useState<Sport | "all">("all");
  async function choose() {
    setWorking(true);
    setError(null);
    setMessage(null);
    try {
      setDraft(await pickActivities());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed.");
    } finally {
      setWorking(false);
    }
  }
  async function save() {
    if (!draft) return;
    setError(null);
    try {
      const result = await mutate((repo) =>
        repo.importActivities(draft.activities),
      );
      setDraft(null);
      setMessage(
        `${result.created} imported, ${result.updated} updated. Repeated imports update matching records.`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed.");
    }
  }
  async function share() {
    setWorking(true);
    setError(null);
    try {
      await shareActivities(
        activities
          .filter((a) => selected.includes(a.activity.id))
          .map((a) => a.activity),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed.");
    } finally {
      setWorking(false);
    }
  }
  const locked = working || busy;
  return (
    <Screen>
      <Title>Activities.</Title>
      <Body muted>Your library, on your phone.</Body>
      <Button
        variant="primary"
        loading={working}
        disabled={busy}
        onPress={() => void choose()}
      >
        Import TCX / FitOps file
      </Button>
      {error ? <Notice>{error}</Notice> : null}
      {message ? <Notice>{message}</Notice> : null}
      {draft ? (
        <Card label="Review import">
          <Body>{draft.name}</Body>
          <Body>
            {draft.activities.length} activities to import
          </Body>
          {draft.activities.map((a, i) => (
            <View key={`${a.id}-${i}`} style={{ gap: 4 }}>
              <Body>{a.name}</Body>
              <Body muted size={13}>
                {a.sport} · {dateLabel(a.start_date)} ·{" "}
                {(a.distance_m / 1000).toFixed(2)} km ·{" "}
                {duration(a.duration_seconds)} · {a.samples.length} samples
              </Body>
              {a.provider === "file" ? (
                <Choice
                  label={`Sport for ${a.name}`}
                  value={a.sport}
                  options={[
                    { value: "Run", label: "Running" },
                    { value: "Ride", label: "Cycling" },
                    { value: "Walk", label: "Walking" },
                    { value: "Other", label: "Other" },
                  ]}
                  onChange={(next) =>
                    setDraft((current) =>
                      current
                        ? {
                            ...current,
                            activities: current.activities.map((item, index) =>
                              index === i ? { ...item, sport: next } : item,
                            ),
                          }
                        : null,
                    )
                  }
                />
              ) : null}
            </View>
          ))}
          <Notice>
            Check sport and date. Matching records update; missing samples may limit estimates.
          </Notice>
          <Button variant="primary" loading={busy} onPress={() => void save()}>
            Save to this phone
          </Button>
          <Button disabled={locked} onPress={() => setDraft(null)}>
            Cancel import
          </Button>
        </Card>
      ) : null}
      <Choice
        label="Filter by sport"
        value={sport}
        onChange={setSport}
        options={[
          { value: "all", label: "All" },
          { value: "Run", label: "Runs" },
          { value: "Ride", label: "Rides" },
          { value: "Walk", label: "Walks" },
          { value: "Other", label: "Other" },
        ]}
      />
      {activities
        .filter((a) => sport === "all" || a.activity.sport === sport)
        .map(({ activity: a, metrics: m }) => (
          <Card key={a.id}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Open ${a.name}`}
              onPress={() =>
                router.push({
                  pathname: "/activity/[id]",
                  params: { id: a.id },
                })
              }
              style={{ minHeight: 48, justifyContent: "center" }}
            >
              <Body>{a.name} ↗</Body>
            </Pressable>
            <Body muted size={13}>
              {dateLabel(a.start_date)} · {a.sport} ·{" "}
              {a.provider === "file" ? "File import" : "Huawei"}
            </Body>
            <Row
              label="Distance / elapsed time"
              value={`${(a.distance_m / 1000).toFixed(2)} km · ${duration(a.duration_seconds)}`}
            />
            <Row
              label="Stress estimate"
              value={
                m.tss.value === null
                  ? "Unavailable"
                  : `${m.tss.value.toFixed(1)} TSS`
              }
            />
            <Pressable
              accessibilityRole="checkbox"
              accessibilityLabel={`Select ${a.name} for export`}
              accessibilityState={{ checked: selected.includes(a.id) }}
              onPress={() =>
                setSelected((ids) =>
                  ids.includes(a.id)
                    ? ids.filter((id) => id !== a.id)
                    : [...ids, a.id],
                )
              }
              style={{
                minHeight: 48,
                justifyContent: "center",
                borderWidth: 1,
                borderColor: colors.border,
                padding: 12,
                borderRadius: 8,
              }}
            >
              <Body>
                {selected.includes(a.id)
                  ? "✓ Selected for export"
                  : "□ Select for export"}
              </Body>
            </Pressable>
          </Card>
        ))}
      {!activities.length ? (
        <Card label="No activities yet">
          <Body>
            Import a TCX activity or FitOps export to start your library.
          </Body>
          <Disclosure label="Supported files">
            <Body muted size={13}>
              Choose a .tcx recording or FitOps .json export. Import stays on this
              phone. Heart-rate and pace estimates need timestamped samples and
              your calibration.
            </Body>
          </Disclosure>
        </Card>
      ) : null}
      {activities.length &&
      sport !== "all" &&
      !activities.some((a) => a.activity.sport === sport) ? (
        <Notice>No activities match this sport.</Notice>
      ) : null}
      {selected.length ? (
        <>
          <Body>{selected.length} selected</Body>
          <Button
            disabled={locked}
            onPress={() =>
              Alert.alert(
                "Export selected activities?",
                "The JSON file includes dates, summaries, and available heart-rate/pace samples. It is not encrypted. Choose a trusted destination. Huawei credentials are never included.",
                [
                  { text: "Cancel", style: "cancel" },
                  { text: "Export", onPress: () => void share() },
                ],
              )
            }
          >
            Export selected records
          </Button>
          <Button disabled={locked} onPress={() => setSelected([])}>
            Clear selection
          </Button>
        </>
      ) : null}
    </Screen>
  );
}
