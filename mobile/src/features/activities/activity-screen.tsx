import { Alert } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import {
  Body,
  Button,
  Card,
  Disclosure,
  MetricValue,
  Notice,
  Row,
  Screen,
  Title,
} from "@/components/ui";
import { useApp } from "@/providers/app-provider";
import { dateLabel, duration, methodLabel } from "../format";

export default function ActivityScreen() {
  const { id } = useLocalSearchParams<{ id: string }>(),
    { activities, mutate, busy } = useApp(),
    router = useRouter();
  const record = activities.find((a) => a.activity.id === id);
  if (!record)
    return (
      <Screen>
        <Title>Activity unavailable.</Title>
        <Body>This record may have been deleted.</Body>
        <Button onPress={() => router.replace("/activities")}>
          Back to activities
        </Button>
      </Screen>
    );
  const { activity: a, metrics: m } = record;
  return (
    <Screen>
      <Button onPress={() => router.replace("/activities")}>
        ← Activities
      </Button>
      <Title>{a.name}</Title>
      <Body muted>
        {dateLabel(a.start_date)} · {a.sport}
      </Body>
      <Card label="Activity">
        <Row
          label="Distance"
          value={`${(a.distance_m / 1000).toFixed(2)} km`}
        />
        <Row label="Elapsed time" value={duration(a.duration_seconds)} />
        <Row
          label="Average HR (measured intervals)"
          value={
            m.average_heartrate_bpm === null
              ? "Unavailable"
              : `${m.average_heartrate_bpm} beats/min`
          }
        />
        <Row
          label="HR coverage"
          value={`${Math.round((m.hr_coverage_seconds / a.duration_seconds) * 100)}%`}
        />
        <Row
          label="Source"
          value={a.provider === "file" ? "File import" : "Huawei Health"}
        />
      </Card>
      <Card label="Activity stress">
        <MetricValue
          value={m.tss.value?.toFixed(1) ?? "—"}
          unit="TSS estimate"
        />
        <Body muted>{methodLabel(m.tss.method)}</Body>
        {m.tss.reason ? <Notice>{m.tss.reason}</Notice> : null}
        <Disclosure label="How stress is estimated">
          <Body muted size={13}>
            Elapsed hours × intensity² × 100. HR intensity uses measured average
            HR / LTHR; pace intensity uses average speed / threshold speed. This
            is not a normalized-power or proprietary hrTSS calculation.
          </Body>
        </Disclosure>
      </Card>
      <Card label="Running VO₂max · estimate">
        <MetricValue
          value={m.vo2max.value?.toFixed(1) ?? "—"}
          unit="ml/kg/min"
        />
        {m.vo2max.reason ? <Notice>{m.vo2max.reason}</Notice> : null}
        <Disclosure label="How VO₂max is estimated">
          <Body muted size={13}>
            Daniels pace model with at least 10 continuous minutes and 1.5 km
            near threshold: 90% of LTHR or 80% of maximum HR. A running-performance
            estimate, not a laboratory measurement. HR, speed, terrain, and effort
            affect it.
          </Body>
        </Disclosure>
      </Card>
      <Card label="Time in HR zones">
        {m.zones.length ? (
          m.zones.map((z) => (
            <Row
              key={z.number}
              label={`Zone ${z.number}`}
              value={`${duration(z.seconds)} · ${Math.round((z.seconds / a.duration_seconds) * 100)}%`}
            />
          ))
        ) : (
          <Body muted>Save calibration for this sport to see zone time.</Body>
        )}
        <Row
          label="Unclassified / missing"
          value={duration(m.unclassified_seconds)}
        />
        <Disclosure label="Missing-data handling">
          <Body muted size={13}>
            Gaps over 30 seconds are excluded. The last HR sample is not extended
            beyond its timestamp.
          </Body>
        </Disclosure>
      </Card>
      <Disclosure label="Calculation details">
        <Body muted size={13}>
          Calculation {m.calculation_version} · calibration {m.calibration_version ?? "not set"}.
          Saving calibration recalculates existing activities for the same sport.
        </Body>
      </Disclosure>
      <Button
        variant="danger"
        disabled={busy}
        onPress={() =>
          Alert.alert(
            "Delete this activity?",
            "This removes the local record and samples from this phone. Exported copies and original source files are unaffected.",
            [
              { text: "Cancel", style: "cancel" },
              {
                text: "Delete",
                style: "destructive",
                onPress: () =>
                  void mutate((repo) => repo.deleteActivity(a.id))
                    .then(() => router.replace("/activities"))
                    .catch(() => {}),
              },
            ],
          )
        }
      >
        Delete activity
      </Button>
    </Screen>
  );
}
