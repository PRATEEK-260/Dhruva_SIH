import { CircleDot, CircleSlash } from "lucide-react";
import type { EvidenceItem, TraceStep } from "../shared/api/client";
import type { Capsule } from "../shared/capsule/decode";
import { kmToNm } from "../shared/harbour";
import type { Language } from "../shared/capsule/codebook";
import { t, type UiKey } from "../shared/i18n";
import uiStrings from "../shared/ui-strings.json";

/** A row's name in the language when the screen text has it, else English. */
function rowName(key: string, lang: Language): string {
  const k = `ev_${key}` as UiKey;
  return k in uiStrings.en ? t(k, lang) : (NAMES[key] ?? key);
}

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
  chlorophyll_30d: "Chlorophyll, last 30 days",
  chlorophyll_baseline: "Chlorophyll, usual for these weeks",
  chlorophyll_change_pct: "Chlorophyll change",
  baseline_years: "Years compared",
  sst_30d: "Sea temperature, last 30 days",
  sst_baseline: "Sea temperature, usual for these weeks",
  sst_difference: "Sea temperature difference",
  storm_distance_nm: "IMD system's centre",
  boundary_1_nm: "Nearest boundary line",
  boundary_2_nm: "Next boundary line",
  boundary_3_nm: "Third boundary line",
  thunderstorm_from: "Thunderstorm forecast from",
  thunder_window_hours: "Thunderstorm forecast window",
  high_water: "High water",
  low_water: "Low water",
  productive_distance_nm: "Productive water",
  productive_chl: "Chlorophyll there",
  productive_sst: "Sea temperature there",
  favourable_sst_low: "Favourable temperature from (provisional)",
  favourable_sst_high: "Favourable temperature to (provisional)",
  route_distance_nm: "Straight line to the zone",
  route_max_wave: "Highest wave along the line",
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

/** Which limit a rule was checked against. A Safe row is compared with the
 * caution limit and a No-go row with the no-go limit, so "limit 2 m" beside one
 * and "limit 3 m" beside the other is one table, not two standards. */
function limitPhrase(ruleId: string): string {
  const [, suffix = ""] = ruleId.split("-");
  if (suffix.startsWith("S")) return "Below the caution limit of";
  if (suffix.startsWith("C")) return "At or above the caution limit of";
  if (suffix.startsWith("N")) return "At or above the no-go limit of";
  if (suffix.startsWith("A")) return "Within";
  return "Limit";
}

export function sourceName(datasetId: string): string {
  if (datasetId === "open_meteo_marine") return "Open-Meteo marine forecast";
  if (datasetId === "open_meteo_forecast") return "Open-Meteo weather forecast";
  if (datasetId === "open_meteo_archive") return "Open-Meteo archive (ERA5)";
  // Query #7's satellite records (backend analytics/baseline.py).
  if (datasetId === "copernicus_globcolour_my") return "Copernicus GlobColour satellite chlorophyll";
  if (datasetId === "copernicus_ostia_nrt") return "OSTIA satellite sea temperature (Copernicus)";
  if (datasetId === "copernicus_ostia_rep") return "OSTIA satellite sea temperature record (Copernicus)";
  if (datasetId.startsWith("cmems") || datasetId.startsWith("copernicus")) return "Copernicus Marine";
  if (datasetId === "incois_pfz") return "INCOIS fishing-zone advisory";
  if (datasetId === "marine_regions") return "Marine Regions (indicative, not legal)";
  if (datasetId === "copernicus_globcolour_nrt") return "Copernicus GlobColour satellite chlorophyll";
  if (datasetId === "provisional_range") return "Provisional range, not an INCOIS criterion";
  // A warning distance comes from an IMD National Bulletin read from its PDF,
  // live or replayed with a past storm, or from a labelled test input.
  if (datasetId === "imd_rsmc_bulletin") return "IMD National Bulletin, RSMC New Delhi";
  if (datasetId === "risk_engine") return "Test input: cyclone placed by hand";
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

/** A clock-time row (unit "h IST") as HH:MM, the way the sentence says it. */
function clockOf(v: number): string {
  const h = Math.floor(v + 1e-9);
  const m = Math.round((v - h) * 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function fmt(v: number): string {
  return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
}

export function EvidenceList({
  items,
  capsule,
  lang = "en",
}: {
  items: EvidenceItem[];
  capsule: Capsule;
  lang?: Language;
}) {
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
              <p className="font-semibold text-ink">{rowName(item.key, lang)}</p>
              <p className="text-sm text-ink-soft leading-snug">
                {sourceName(item.dataset_id)}
                {item.is_forecast ? ", forecast" : ""}
                <br />
                {item.baseline_years && item.window_end
                  ? `same 30 days in ${item.baseline_years.join(", ")}; ${item.cell}`
                  : item.window_start && item.window_end
                    ? `mean of ${advisoryDate(item.window_start)} to ${advisoryDate(item.window_end)}; ${item.cell}`
                    : item.dataset_id === "incois_pfz"
                  ? `issued ${advisoryDate(item.valid_time)}, nearest point of the line`
                  : item.dataset_id === "imd_rsmc_bulletin"
                    ? `${item.upstream_dataset_id ?? ""}; centre ${item.cell} at ${istTime(item.valid_time)}`
                    : `valid ${istTime(item.valid_time)}`}
                {item.offset_km ? `, grid cell ${fmt(kmToNm(item.offset_km))} nm away` : ""}
              </p>
              {item.rule_id && (
                <p className="text-sm text-ink-soft">
                  {item.threshold != null
                    ? `${limitPhrase(item.rule_id)} ${fmt(inKm ? kmToNm(item.threshold) : item.threshold)} ${unit}`
                    : `Rule ${item.rule_id}`}
                  {item.threshold != null && (item.unit === "m" || item.unit === "kt") && (
                    <span className={item.threshold_source ? "block font-semibold text-ink" : "block"}>
                      {item.threshold_source
                        ? `Limit from ${item.threshold_source}`
                        : "Provisional limit, not yet an official criterion"}
                    </span>
                  )}
                </p>
              )}
            </div>
            <div className="text-right shrink-0">
              <p className="text-2xl font-extrabold text-ink tabular-nums leading-none">
                {item.unit === "h IST" ? clockOf(item.value) : fmt(shownValue)}
                <span className="text-base font-semibold text-ink-soft ml-1">{item.unit === "h IST" ? "IST" : unit}</span>
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
