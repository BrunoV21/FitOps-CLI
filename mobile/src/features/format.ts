export const methodLabel = (method: string) =>
  ({
    "hr-stress-v1": "HR-based stress approximation",
    "pace-stress-v1": "Pace-based stress approximation",
    "daniels-streams-v1": "FitOps Daniels running estimate",
    unavailable: "Needs calibration",
  })[method] ?? method;
export function duration(seconds: number): string {
  const s = Math.round(seconds);
  return s >= 3600
    ? `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`
    : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
export const dateLabel = (date: string) =>
  new Date(date).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
