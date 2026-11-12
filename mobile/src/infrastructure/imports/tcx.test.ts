import { parseTcx } from './tcx';
import { exportActivities, parseExchange } from '../transfer/exchange';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const tcx = `<TrainingCenterDatabase><Activities><Activity Sport="Running"><Id>2026-11-01T08:00:00Z</Id><Lap><TotalTimeSeconds>20</TotalTimeSeconds><DistanceMeters>80</DistanceMeters><Track><Trackpoint><Time>2026-11-01T08:00:00Z</Time><DistanceMeters>0</DistanceMeters><HeartRateBpm><Value>150</Value></HeartRateBpm></Trackpoint><Trackpoint><Time>2026-11-01T08:00:20Z</Time><DistanceMeters>80</DistanceMeters></Trackpoint></Track></Lap></Activity></Activities></TrainingCenterDatabase>`;
test('TCX maps units, time, identity, sport and preserves missing HR', () => {
  const [a] = parseTcx(tcx);
  expect(a.sport).toBe('Run'); expect(a.distance_m).toBe(80); expect(a.duration_seconds).toBe(20);
  expect(a.samples[0].heartrate_bpm).toBe(150); expect(a.samples[1].heartrate_bpm).toBeNull();
  expect(a.samples[1].time_seconds).toBe(20);
  expect(parseTcx(tcx)[0].id).toBe(a.id);
});
test('TCX refuses malformed input, entities, missing dates, and empty activities', () => {
  expect(() => parseTcx('<broken>')).toThrow();
  expect(() => parseTcx('<!DOCTYPE xml>'+tcx)).toThrow('document types');
  expect(() => parseTcx(tcx.replaceAll('2026-11-01T08:00:00Z','bad'))).toThrow('timezone');
  expect(() => parseTcx('<TrainingCenterDatabase/>')).toThrow('1–100');
});
test('exchange is round-trip safe and excludes unapproved fields', () => {
  const [a] = parseTcx(tcx);
  expect(parseExchange(exportActivities([a]))).toEqual([a]);
  const payload = JSON.parse(exportActivities([a])); payload.access_token = 'not-a-real-token';
  expect(() => parseExchange(JSON.stringify(payload))).toThrow();
  payload.version = 2; expect(() => parseExchange(JSON.stringify(payload))).toThrow();
});
test('exchange validates chronological data and recomputes untrusted local IDs', () => {
  const [a] = parseTcx(tcx); a.id = 'forged';
  expect(parseExchange(exportActivities([a]))[0].id).not.toBe('forged');
  a.samples.reverse(); expect(() => exportActivities([a])).toThrow('chronological');
});

test('TCX rejects normalized invalid dates, timezone-free dates, and excessive nesting', () => {
  expect(() => parseTcx(tcx.replaceAll('2026-11-01', '2026-02-30'))).toThrow('timestamp');
  expect(() => parseTcx(tcx.replaceAll('2026-11-01T08:00:00Z', '2026-11-01T08:00:00'))).toThrow('timezone');
  const nested = '<a>'.repeat(70) + 'x' + '</a>'.repeat(70);
  expect(() => parseTcx(nested)).toThrow();
});

test('shared synthetic TCX and FitOps export normalize to identical canonical activities', () => {
  const fixture = (name:string) => readFileSync(resolve(__dirname,'../../../contracts/fixtures',name),'utf8');
  expect(parseTcx(fixture('synthetic-run.tcx'))).toEqual(parseExchange(fixture('synthetic-run.fitops.json')));
});

test('namespaced TCX, timezone offsets, missing HR and duplicate lap boundary samples are supported', () => {
  const namespaced = tcx.replaceAll('<TrainingCenterDatabase>', '<g:TrainingCenterDatabase xmlns:g="urn:test">').replaceAll('</TrainingCenterDatabase>', '</g:TrainingCenterDatabase>')
    .replaceAll('2026-11-01T08:00:00Z','2026-11-01T09:00:00+01:00')
    .replaceAll('2026-11-01T08:00:20Z','2026-11-01T09:00:20+01:00');
  expect(parseTcx(namespaced)).toEqual(parseTcx(tcx));
  const duplicate = tcx.replace('</Track>', '<Trackpoint><Time>2026-11-01T08:00:20Z</Time><DistanceMeters>80</DistanceMeters></Trackpoint></Track>');
  expect(parseTcx(duplicate)[0].samples).toHaveLength(2);
});

test('empty or implausible HR samples stay missing rather than becoming zero or a valid effort', () => {
  const empty = tcx.replace('<Value>150</Value>','<Value/>');
  const invalid = tcx.replace('<Value>150</Value>','<Value>300</Value>');
  expect(parseTcx(empty)[0].samples[0].heartrate_bpm).toBeNull();
  expect(parseTcx(invalid)[0].samples[0].heartrate_bpm).toBeNull();
});

test('an exchange rejects duplicate source identities consistently with desktop', () => {
  const [activity] = parseTcx(tcx);
  expect(() => exportActivities([activity, activity])).toThrow('repeated source identities');
});
