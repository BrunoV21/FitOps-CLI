import { useRouter } from "expo-router";
import {
  Body,
  Button,
  Card,
  Disclosure,
  MetricValue,
  Row,
  Screen,
  Title,
} from "@/components/ui";
import { useApp } from "@/providers/app-provider";
import { dateLabel, methodLabel } from "../format";

export default function OverviewScreen() {
  const { activities, calibrations } = useApp(),
    router = useRouter();
  const latest = activities.find((a) => a.metrics.vo2max.value !== null);
  return (
    <Screen>
      <Title>Your metrics.</Title>
      <Body muted>Local data. Clear signals.</Body>
      {!activities.length ? (
        <Card label="Welcome to FitOps">
          <Body>
            Import an activity, then set your heart-rate zones.
          </Body>
          <Button variant="primary" onPress={() => router.push("/activities")}>
            Import an activity
          </Button>
          <Button onPress={() => router.push("/zones")}>
            Set your calibration
          </Button>
        </Card>
      ) : null}
      <Card label="Running VO₂max · estimate">
        <MetricValue
          value={latest?.metrics.vo2max.value?.toFixed(1) ?? "—"}
          unit="ml/kg/min"
        />
        {latest ? (
          <>
            <Body>Last estimate · {dateLabel(latest.activity.start_date)}</Body>
            <Body muted size={14}>
              {latest.activity.name}
            </Body>
          </>
        ) : (
          <Body muted>
            {calibrations.some((c) => c.sport === "Run")
              ? "Import a qualifying run with HR and speed samples."
              : "Set running LTHR or maximum HR, then import a qualifying run."}
          </Body>
        )}
        <Disclosure label="About this estimate">
          <Body muted size={13}>
            Running-performance estimate, not a laboratory measurement. Heat,
            hills, sensor error, and effort affect the result.
          </Body>
        </Disclosure>
      </Card>
      <Card label="Recent activity stress">
        {activities.length ? (
          activities
            .slice(0, 5)
            .map(({ activity: a, metrics: m }) => (
              <Row
                key={a.id}
                label={`${dateLabel(a.start_date)} · ${a.sport}`}
                value={
                  m.tss.value === null
                    ? "Unavailable"
                    : `${m.tss.value.toFixed(1)} TSS`
                }
              />
            ))
        ) : (
          <Body muted>No activities imported yet.</Body>
        )}
        <Body muted size={13}>
          Estimates · method shown in activity details.
        </Body>
      </Card>
      <Card label="Heart-rate calibration">
        {calibrations.length ? (
          calibrations.map((c) => (
            <Row
              key={c.sport}
              label={c.sport}
              value={`${c.method.toUpperCase()} · ${dateLabel(c.calibrated_at)}`}
            />
          ))
        ) : (
          <Body muted>No calibration saved.</Body>
        )}
        <Button onPress={() => router.push("/zones")}>Review zones</Button>
      </Card>
      {activities.some((a) => a.metrics.vo2max.value !== null) ? (
        <Card label="VO₂max history">
          {activities
            .filter((a) => a.metrics.vo2max.value !== null)
            .slice(0, 10)
            .map(({ activity: a, metrics: m }) => (
              <Row
                key={a.id}
                label={dateLabel(a.start_date)}
                value={`${m.vo2max.value?.toFixed(1)} ml/kg/min`}
              />
            ))}
          <Body muted size={13}>
            {methodLabel("daniels-streams-v1")} · latest 10 qualifying
            activities
          </Body>
        </Card>
      ) : null}
    </Screen>
  );
}
