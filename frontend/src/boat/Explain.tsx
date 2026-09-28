import { CircleDot, CircleSlash } from "lucide-react";
import type { EvidenceItem, TraceStep } from "../shared/api/client";
import type { Capsule } from "../shared/capsule/decode";
import { kmToNm } from "../shared/harbour";

const NAMES: Record<string, string> = {
  wave_height: "Wave height",
  wave_period: "Wave period",
  wind_speed: "Wind",
  wind_direction: "Wind from",
  sst: "Sea temperature",
  chlorophyll: "Chlorophyll",
  current_speed: "Current",
  current_direction: "Current towards",
  cyclone_distance: "Cyclone distance",
  lightning_distance: "Lightning distance",
  pfz_distance: "Potential fishing zone",
};

const UNITS: Record<string, string> = { degC: "°C", degree: "°", "mg m-3": "mg/m³" };

// The capsule field each reading is sent as, so the card can say "sent as 0.25 m"
// next to a 0.28 m reading: the spoken figure is the quantised one.
const SENT_AS: Record<string, keyof Capsule> = {
  wave_height: "wave_hs_m",
  wind_speed: "wind_kt",
  current_speed: "curr_kt",
  sst: "sst_c",
  pfz_distance: "pfz_dist_nm",
};

export function sourceName(datasetId: string): string {
  if (datasetId === "open_meteo_marine") return "Open-Meteo marine forecast";
  if (datasetId === "open_meteo_forecast") return "Open-Meteo weather forecast";
  if (datasetId.startsWith("cmems") || datasetId.startsWith("copernicus")) return "Copernicus Marine";
  // No live IMD feed is wired, so every warning distance today is a test input.
  if (datasetId === "incois_pfz") return "INCOIS fishing-zone advisory";
  if (datasetId === "risk_engine") return "Simulated cyclone warning (test input)";
  return datasetId;
}

export function istTime(iso: string | null | undefined): string {
  if (!iso) return "time not given";
  return (
    new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
    }) + " IST"
  );
}

/** An advisory's own date, which is a day, not an instant. */
export function advisoryDate(iso: string | null | undefined): string {
  if (!iso) return "date not given";
  return new Date(iso).toLocaleDateString("en-IN", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
}

function fmt(v: number): string {
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

export function EvidenceList({ items, capsule }: { items: EvidenceItem[]; capsule: Capsule }) {
  return (
    <ul className="divide-y divide-rule">
      {items.map((item) => {
        // One distance unit on the phone: a distance given in km is shown in nm,
        // with the source's own figure beneath it.
        const inKm = item.unit === "km";
        const shownValue = inKm ? kmToNm(item.value) : item.value;
        const unit = inKm ? "nm" : (UNITS[item.unit] ?? item.unit);
        const sentField = SENT_AS[item.key];
        const sent = sentField !== undefined ? (capsule[sentField] as number) : undefined;
        const showSent = sent !== undefined && Math.abs(sent - item.value) > 1e-6;
        return (
          <li key={item.key} className="py-3 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="font-semibold text-ink">{NAMES[item.key] ?? item.key}</p>
              <p className="text-sm text-ink-soft leading-snug">
                {sourceName(item.dataset_id)}
                {item.is_forecast ? ", forecast" : ""}
                <br />
                {item.dataset_id === "incois_pfz"
                  ? `issued ${advisoryDate(item.valid_time)}, nearest point of the line`
                  : `valid ${istTime(item.valid_time)}`}
                {item.offset_km ? `, grid cell ${fmt(kmToNm(item.offset_km))} nm away` : ""}
              </p>
              {item.rule_id && (
                <p className="text-sm text-ink-soft">
                  Rule {item.rule_id}
                  {item.threshold != null
                    ? `, limit ${fmt(inKm ? kmToNm(item.threshold) : item.threshold)} ${unit}`
                    : ""}
                </p>
              )}
            </div>
            <div className="text-right shrink-0">
              <p className="text-2xl font-extrabold text-ink tabular-nums leading-none">
                {fmt(shownValue)}
                <span className="text-base font-semibold text-ink-soft ml-1">{unit}</span>
              </p>
              {inKm && <p className="text-xs text-ink-soft mt-1">given as {fmt(item.value)} km</p>}
              {showSent && (
                <p className="text-xs text-ink-soft mt-1">
                  sent as {fmt(sent)} {unit}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// Offline: only the figures the spoken sentence uses, straight from the capsule.
const SLOT_FIGURES: Record<string, { name: string; field: keyof Capsule; unit: string }> = {
  wave_hs_m: { name: "Wave height", field: "wave_hs_m", unit: "m" },
  wave_hs_ft: { name: "Wave height", field: "wave_hs_m", unit: "m" },
  wind_kt: { name: "Wind", field: "wind_kt", unit: "kt" },
  wind_kmh: { name: "Wind", field: "wind_kt", unit: "kt" },
  curr_kt: { name: "Current", field: "curr_kt", unit: "kt" },
  sst_c: { name: "Sea temperature", field: "sst_c", unit: "°C" },
  pfz_dist_nm: { name: "Fishing zone", field: "pfz_dist_nm", unit: "nm" },
  bnd_dist_nm: { name: "Boundary", field: "bnd_dist_nm", unit: "nm" },
  valid_hours: { name: "Valid for", field: "valid_hours", unit: "h" },
};

export function hasFigures(slots: string[]): boolean {
  return slots.some((s) => s in SLOT_FIGURES);
}

export function CapsuleFigures({ capsule, slots }: { capsule: Capsule; slots: string[] }) {
  const seen = new Set<string>();
  const rows = slots
    .map((s) => SLOT_FIGURES[s])
    .filter((r) => r && !seen.has(r.field) && seen.add(r.field));
  if (rows.length === 0) return null;
  return (
    <ul className="grid grid-cols-2 gap-3">
      {rows.map((r) => (
        <li key={r.field} className="rounded-xl bg-mist p-3">
          <p className="text-sm text-ink-soft">{r.name}</p>
          <p className="text-2xl font-extrabold text-ink tabular-nums">
            {fmt(capsule[r.field] as number)}
            <span className="text-base font-semibold text-ink-soft ml-1">{r.unit}</span>
          </p>
        </li>
      ))}
    </ul>
  );
}

export function TracePanel({ steps }: { steps: TraceStep[] }) {
  return (
    <ol className="relative">
      {steps.map((s) => (
        <li key={s.node} className={`flex gap-3 py-2 ${s.ran ? "" : "opacity-45"}`}>
          {s.ran ? (
            <CircleDot className="w-5 h-5 text-sea shrink-0 mt-0.5" aria-label="ran" />
          ) : (
            <CircleSlash className="w-5 h-5 text-ink-soft shrink-0 mt-0.5" aria-label="skipped" />
          )}
          <div className="min-w-0">
            <p className="font-semibold text-ink leading-tight">
              {s.agent}
              {!s.ran && <span className="font-normal text-ink-soft">, skipped</span>}
            </p>
            <p className="text-sm text-ink-soft leading-snug break-words">{s.line}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
