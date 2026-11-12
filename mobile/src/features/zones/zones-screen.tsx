import { useState } from "react";
import { Alert } from "react-native";
import type { Calibration, Sport, ZoneMethod } from "@/domain/activities/types";
import { computeZones, validateCalibration } from "@/domain/calibration/model";
import {
  Body,
  Button,
  Card,
  Choice,
  Disclosure,
  Field,
  Notice,
  Row,
  Screen,
  Title,
} from "@/components/ui";
import { useApp } from "@/providers/app-provider";
import { dateLabel } from "../format";

export default function ZonesScreen() {
  const [sport, setSport] = useState<Sport>("Run");
  return (
    <Screen>
      <Title>Know your zones.</Title>
      <Body muted>Personal heart-rate boundaries.</Body>
      <Choice
        label="Sport"
        value={sport}
        onChange={setSport}
        options={[
          { value: "Run", label: "Running" },
          { value: "Ride", label: "Cycling" },
          { value: "Walk", label: "Walking" },
        ]}
      />
      <CalibrationForm key={sport} sport={sport} />
    </Screen>
  );
}
function CalibrationForm({ sport }: { sport: Sport }) {
  const { calibrations, mutate, busy } = useApp();
  const saved = calibrations.find((c) => c.sport === sport);
  const [method, setMethod] = useState<ZoneMethod>(saved?.method ?? "lthr");
  const [max, setMax] = useState(saved?.max_hr_bpm?.toString() ?? ""),
    [rest, setRest] = useState(saved?.resting_hr_bpm?.toString() ?? ""),
    [lthr, setLthr] = useState(saved?.lthr_bpm?.toString() ?? ""),
    [pace, setPace] = useState(
      saved?.threshold_pace_seconds_per_km?.toString() ?? "",
    ),
    [source, setSource] = useState(saved?.source ?? ""),
    [date, setDate] = useState(
      saved?.calibrated_at.slice(0, 10) ??
        new Date().toISOString().slice(0, 10),
    );
  const [error, setError] = useState<string | null>(null),
    [message, setMessage] = useState<string | null>(null);
  async function save() {
    setError(null);
    setMessage(null);
    try {
      if (
        !/^\d{4}-\d{2}-\d{2}$/.test(date) ||
        new Date(date + "T00:00:00Z").toISOString().slice(0, 10) !== date ||
        date > new Date().toISOString().slice(0, 10)
      )
        throw new Error(
          "Use a valid calibration date, YYYY-MM-DD, no later than today.",
        );
      const n = (text: string) => (text.trim() === "" ? null : Number(text));
      const c: Calibration = {
        sport,
        method,
        max_hr_bpm: n(max),
        resting_hr_bpm: n(rest),
        lthr_bpm: n(lthr),
        threshold_pace_seconds_per_km: sport === "Run" ? n(pace) : null,
        source: source.trim(),
        calibrated_at: date + "T00:00:00Z",
        version: (saved?.version ?? 0) + 1,
      };
      validateCalibration(c);
      await mutate((repo) => repo.saveCalibration(c));
      setMessage(
        "Saved. Activities for this sport have been recalculated.",
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save calibration.");
    }
  }
  return (
    <>
      {saved ? (
        <Card label="Saved zones">
          {computeZones(saved).map((z) => (
            <Row
              key={z.number}
              label={`Z${z.number} · ${z.name}`}
              value={`${z.lower_bpm}${z.upper_bpm === null ? "+" : `–${z.upper_bpm - 1}`} beats/min`}
            />
          ))}
          <Body muted size={13}>
            {saved.method.toUpperCase()} · {dateLabel(saved.calibrated_at)}
          </Body>
          <Disclosure label="Zone details">
            <Body muted size={13}>Source: {saved.source}</Body>
            <Body muted size={13}>
              Lower bounds are inclusive. For HRR/max-HR, values below Zone 1
              remain unclassified.
            </Body>
          </Disclosure>
        </Card>
      ) : (
        <Notice>
          No calibration saved. Enter your confirmed thresholds below.
        </Notice>
      )}
      <Card>
        <Disclosure label={saved ? "Edit calibration" : "Set calibration"} defaultOpen={!saved}>
        <Choice
          label="Zone method"
          value={method}
          onChange={setMethod}
          options={[
            { value: "lthr", label: "LTHR" },
            { value: "hrr", label: "HR reserve" },
            { value: "max-hr", label: "Max HR" },
          ]}
        />
        {method !== "lthr" ? (
          <Field label="Maximum HR · beats/min" keyboardType="number-pad" value={max} onChangeText={setMax}/>
        ) : null}
        {method === "hrr" ? (
          <Field label="Resting HR · beats/min" keyboardType="number-pad" value={rest} onChangeText={setRest}/>
        ) : null}
        {method === "lthr" ? (
          <Field label="Threshold HR (LTHR) · beats/min" keyboardType="number-pad" value={lthr} onChangeText={setLthr}/>
        ) : null}
        <Disclosure label="Optional thresholds">
          {method === "lthr" ? (
            <Field label="Maximum HR · beats/min" keyboardType="number-pad" value={max} onChangeText={setMax}/>
          ) : null}
          {method !== "hrr" ? (
            <Field label="Resting HR · beats/min" keyboardType="number-pad" value={rest} onChangeText={setRest}/>
          ) : null}
          {method !== "lthr" ? (
            <Field label="Threshold HR (LTHR) · beats/min" keyboardType="number-pad" value={lthr} onChangeText={setLthr}/>
          ) : null}
          {sport === "Run" ? (
            <Field label="Threshold pace · seconds/km (optional)" keyboardType="number-pad" value={pace} onChangeText={setPace} placeholder="300 = 5:00/km"/>
          ) : null}
          <Body muted size={13}>LTHR or running threshold pace enables stress estimates.</Body>
        </Disclosure>
        <Field
          label="Calibration source"
          value={source}
          onChangeText={setSource}
          maxLength={200}
          placeholder="e.g. field test"
        />
        <Field
          label="Calibration date · YYYY-MM-DD"
          value={date}
          onChangeText={setDate}
          autoCapitalize="none"
          maxLength={10}
        />
        <Disclosure label="About zone methods">
          <Body muted size={13}>
            LTHR uses threshold HR. HR reserve uses maximum and resting HR.
            Max-HR uses maximum HR. LTHR uses the HRR-corrected aerobic boundary
            when maximum and resting HR are both supplied. These are zone models,
            not automatic threshold measurements.
          </Body>
        </Disclosure>
        <Body muted size={13}>
          Saving recalculates all activities for this sport on this phone.
        </Body>
        {error ? <Notice>{error}</Notice> : null}
        {message ? <Notice>{message}</Notice> : null}
        <Button variant="primary" loading={busy} onPress={() => void save()}>
          Save and recalculate
        </Button>
        {saved ? (
          <Button
            variant="danger"
            disabled={busy}
            onPress={() =>
              Alert.alert(
                "Remove this calibration?",
                "Existing activities for this sport will lose estimates that depend on these settings.",
                [
                  { text: "Cancel", style: "cancel" },
                  {
                    text: "Remove",
                    style: "destructive",
                    onPress: () =>
                      void mutate((repo) => repo.clearCalibration(sport)).catch(
                        () => {},
                      ),
                  },
                ],
              )
            }
          >
            Remove calibration
          </Button>
        ) : null}
        </Disclosure>
      </Card>
    </>
  );
}
