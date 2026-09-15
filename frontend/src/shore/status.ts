import type { AdvisoryLogEntry } from "../shared/api/client";
import { verdictOf } from "../boat/BoatApp";
import { ZONE_LAT_MAX, ZONE_LAT_MIN, ZONE_LON_MAX, ZONE_LON_MIN } from "../shared/capsule/fields";

/** risk_class ("safe" | "caution" | "no_go" | "unknown") to the display label.
 * The one place this comparison happens, so the uppercase/lowercase mismatch
 * that once broke BoatApp's verdict card cannot reappear here silently. */
export function displayStatus(riskClass: string): "NO-GO" | "CAUTION" | "SAFE" | "UNKNOWN" {
  const verdict = verdictOf(riskClass);
  if (verdict === "no_go") return "NO-GO";
  if (verdict === "caution") return "CAUTION";
  if (verdict === "safe") return "SAFE";
  return "UNKNOWN";
}

export type RequestFilter = "all" | "safe" | "caution" | "no_go";

export function filterRequests(entries: AdvisoryLogEntry[], filter: RequestFilter): AdvisoryLogEntry[] {
  return filter === "all" ? entries : entries.filter((e) => e.risk_class === filter);
}

/** The capsule can only address positions inside its zone grid; an advisory
 * for a point outside it would encode a clamped, wrong position. */
export function inCapsuleGrid(lat: number, lon: number): boolean {
  return lat >= ZONE_LAT_MIN && lat < ZONE_LAT_MAX && lon >= ZONE_LON_MIN && lon < ZONE_LON_MAX;
}

export function ageLabel(then: Date, now: Date): string {
  const seconds = Math.max(0, Math.round((now.getTime() - then.getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  return `${Math.floor(minutes / 60)} h ago`;
}
