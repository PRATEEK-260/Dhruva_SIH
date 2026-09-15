import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { AlertTriangle, CheckCircle2, Copy, Loader2, MousePointerClick, ShieldAlert, ShieldCheck, HelpCircle } from "lucide-react";
import type { AdvisoryResponse, EvidenceBundle, EvidenceItem } from "../shared/api/client";
import { decodeCapsule } from "../shared/capsule/decode";
import { LANGUAGES, renderReason, type Language } from "../shared/capsule/codebook";
import { CAPSULE_BYTES, SEGMENT_BITS, TOTAL_BITS } from "../shared/capsule/fields";
import { displayStatus } from "./status";

export type InspectState =
  | { state: "idle" }
  | { state: "loading"; lat: number; lon: number; when: string | null }
  | { state: "error"; message: string }
  | { state: "ok"; lat: number; lon: number; when: string | null; boatClass: string; response: AdvisoryResponse };

export const BOAT_CLASSES = [
  ["frp_under_12m", "FRP / country craft < 12 m"],
  ["mechanised_12_20m", "Mechanised 12–20 m"],
  ["deep_sea_over_20m", "Deep-sea > 20 m"],
] as const;

const LANGUAGE_NAMES: Record<Language, string> = {
  en: "English", ta: "Tamil", te: "Telugu", ml: "Malayalam", kn: "Kannada", mr: "Marathi",
  kok: "Konkani", gu: "Gujarati", or: "Odia", bn: "Bengali", hi: "Hindi", ur: "Urdu",
};

const VARIABLE_NAMES: Record<string, string> = {
  wave_height: "Wave height (Hs)",
  wave_period: "Wave period",
  wind_speed: "Wind speed",
  wind_direction: "Wind direction",
  current_speed: "Current speed",
  current_direction: "Current direction",
  sst: "Sea surface temp",
  chlorophyll: "Chlorophyll",
};

export function variableName(key: string): string {
  return VARIABLE_NAMES[key] ?? key.replace(/_/g, " ");
}

/** The bundle as the API returns it is untyped JSON; anything without an items
 * array is treated as carrying no evidence rather than trusted blindly. */
export function asBundle(evidence: Record<string, unknown>): EvidenceBundle | null {
  return Array.isArray(evidence.items) ? (evidence as unknown as EvidenceBundle) : null;
}

export function utcStamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace("T", " ")}Z`;
}

interface Props {
  inspect: InspectState;
  boatClass: string;
  onBoatClassChange: (value: string) => void;
}

export function InspectPanel({ inspect, boatClass, onBoatClassChange }: Props) {
  if (inspect.state === "idle") {
    return (
      <div className="h-full flex items-center justify-center gap-3 text-gray-500 text-sm">
        <MousePointerClick className="w-5 h-5" />
        Click the sea, or a request in the list, to run a live advisory for that position.
      </div>
    );
  }
  if (inspect.state === "loading") {
    return (
      <div className="h-full flex items-center justify-center gap-3 text-gray-600 text-sm">
        <Loader2 className="w-5 h-5 animate-spin" />
        Running the advisory graph for {inspect.lat.toFixed(3)}° N, {inspect.lon.toFixed(3)}° E
        {inspect.when ? ` as of ${utcStamp(inspect.when)}` : ""}…
      </div>
    );
  }
  if (inspect.state === "error") {
    return (
      <div role="alert" className="h-full flex items-center justify-center gap-3 text-danger text-sm font-medium">
        <AlertTriangle className="w-5 h-5" />
        {inspect.message}
      </div>
    );
  }

  const { response, lat, lon, when } = inspect;
  const bundle = asBundle(response.evidence);

  return (
    <div className="flex gap-4 h-full min-h-0 flex-col xl:flex-row">
      <VerdictCard
        response={response}
        bundle={bundle}
        lat={lat}
        lon={lon}
        when={when}
        boatClass={boatClass}
        onBoatClassChange={onBoatClassChange}
      />
      <EvidenceTable items={bundle?.items ?? []} />
      <CapsuleCard capsuleBase32={response.capsule_base32} />
    </div>
  );
}

function VerdictCard({
  response, bundle, lat, lon, when, boatClass, onBoatClassChange,
}: {
  response: AdvisoryResponse;
  bundle: EvidenceBundle | null;
  lat: number;
  lon: number;
  when: string | null;
  boatClass: string;
  onBoatClassChange: (value: string) => void;
}) {
  const status = displayStatus(response.risk_class);
  const tone =
    status === "NO-GO" ? "bg-danger text-white" :
    status === "CAUTION" ? "bg-caution text-white" :
    status === "SAFE" ? "bg-safe text-white" : "bg-gray-500 text-white";
  const Icon = status === "NO-GO" ? ShieldAlert : status === "SAFE" ? ShieldCheck : status === "CAUTION" ? AlertTriangle : HelpCircle;

  return (
    <section className="xl:w-80 shrink-0 bg-white rounded-lg border border-gray-200 flex flex-col overflow-hidden">
      <div className={`px-4 py-3 flex items-center gap-3 ${tone}`}>
        <Icon className="w-7 h-7 shrink-0" />
        <div>
          <p className="text-xl font-extrabold tracking-wide leading-none">{status}</p>
          <p className="text-xs opacity-90 mt-1">{lat.toFixed(3)}° N, {lon.toFixed(3)}° E</p>
        </div>
      </div>
      <div className="p-3 space-y-2 text-xs overflow-y-auto">
        {when && (
          <p className="bg-slate-800 text-white rounded px-2 py-1 font-semibold">
            Replay — conditions as of {utcStamp(when)}, not the sea right now.
          </p>
        )}
        <label className="flex items-center justify-between gap-2">
          <span className="text-gray-500">Boat class</span>
          <select
            value={boatClass}
            onChange={(e) => onBoatClassChange(e.target.value)}
            className="border border-gray-200 rounded px-2 py-1 bg-gray-50"
          >
            {BOAT_CLASSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        {bundle && bundle.fired_rules.length > 0 && (
          <p><span className="text-gray-500">Rules fired: </span><span className="font-mono">{bundle.fired_rules.join(", ")}</span></p>
        )}
        {bundle?.provisional_thresholds && (
          <p className="text-caution font-semibold">Thresholds are provisional placeholders, not INCOIS criteria.</p>
        )}
        <p className={response.firewall_passed ? "text-safe font-semibold" : "text-danger font-semibold"}>
          {response.firewall_passed ? "Numeric firewall: every number traced to evidence" : "Numeric firewall failed — template narration shown"}
        </p>
        <p className="text-gray-700 leading-snug">{response.narration}</p>
        <p className="text-gray-500 italic">{response.notice}</p>
      </div>
    </section>
  );
}

function EvidenceTable({ items }: { items: EvidenceItem[] }) {
  return (
    <section className="flex-1 min-w-0 bg-white rounded-lg border border-gray-200 flex flex-col overflow-hidden">
      <h3 className="px-4 py-2 border-b border-gray-100 font-bold text-sm">Evidence</h3>
      {items.length === 0 ? (
        <p className="p-4 text-sm text-gray-500">No source answered for this position, so no figures are shown.</p>
      ) : (
        <div className="overflow-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-gray-500 bg-gray-50 sticky top-0">
              <tr>
                <th className="px-3 py-1.5 font-medium">Variable</th>
                <th className="px-3 py-1.5 font-medium">Value</th>
                <th className="px-3 py-1.5 font-medium">Threshold</th>
                <th className="px-3 py-1.5 font-medium">Source</th>
                <th className="px-3 py-1.5 font-medium">Cell that answered</th>
                <th className="px-3 py-1.5 font-medium">Valid</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={`${item.key}-${item.dataset_id}`} className="border-t border-gray-100 align-top">
                  <td className="px-3 py-1.5 font-medium text-gray-800">{variableName(item.key)}</td>
                  <td className="px-3 py-1.5 font-bold text-gray-900 whitespace-nowrap">{item.value} {item.unit}</td>
                  <td className="px-3 py-1.5 whitespace-nowrap">
                    {item.threshold != null ? <>{item.threshold} {item.unit} <span className="font-mono text-gray-500">{item.rule_id}</span></> : "—"}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-gray-600 break-all">{item.dataset_id}</td>
                  <td className="px-3 py-1.5 text-gray-600 whitespace-nowrap">
                    {item.cell}{item.offset_km != null && <span className="text-gray-400"> ({item.offset_km} km away)</span>}
                  </td>
                  <td className="px-3 py-1.5 text-gray-600 whitespace-nowrap">
                    {utcStamp(item.valid_time)}{" "}
                    <span className={`px-1 rounded text-[10px] font-semibold ${item.is_forecast ? "bg-blue-50 text-blue-700" : "bg-gray-100 text-gray-700"}`}>
                      {item.is_forecast ? "forecast" : "observation"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function CapsuleCard({ capsuleBase32 }: { capsuleBase32: string }) {
  const [language, setLanguage] = useState<Language>("ta");
  const [qrSvg, setQrSvg] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!capsuleBase32) return;
    let live = true;
    QRCode.toString(capsuleBase32, { type: "svg", margin: 1 }).then((svg) => live && setQrSvg(svg));
    return () => { live = false; };
  }, [capsuleBase32]);

  let spoken: { text: string; degraded: boolean } | null = null;
  let decodeError: string | null = null;
  if (capsuleBase32) {
    try {
      spoken = renderReason(decodeCapsule(capsuleBase32), language);
    } catch (err) {
      decodeError = err instanceof Error ? err.message : String(err);
    }
  }

  const usedPct = Math.round((TOTAL_BITS / SEGMENT_BITS) * 100);

  return (
    <section className="xl:w-[26rem] shrink-0 bg-white rounded-lg border border-gray-200 p-3 flex flex-col gap-2 overflow-y-auto">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-sm">Capsule for handoff</h3>
        <select
          aria-label="Capsule language"
          value={language}
          onChange={(e) => setLanguage(e.target.value as Language)}
          className="text-xs border border-gray-200 rounded px-2 py-1 bg-gray-50"
        >
          {LANGUAGES.map((l) => <option key={l} value={l}>{LANGUAGE_NAMES[l]}</option>)}
        </select>
      </div>

      {!capsuleBase32 ? (
        <p className="text-sm text-danger">The graph returned no capsule for this position.</p>
      ) : (
        <div className="flex gap-3">
          <div
            className="w-28 h-28 shrink-0 bg-white border border-gray-200 rounded [&>svg]:w-full [&>svg]:h-full"
            aria-label="Capsule QR code"
            dangerouslySetInnerHTML={{ __html: qrSvg }}
          />
          <div className="flex-1 min-w-0 space-y-2">
            <div>
              <div className="flex justify-between items-baseline text-xs">
                <span className="font-semibold text-gray-500 uppercase">Payload</span>
                <span className="text-gray-500">{CAPSULE_BYTES} bytes</span>
              </div>
              <p className="font-bold text-gray-800 text-sm">{TOTAL_BITS} / {SEGMENT_BITS} bits <span className="text-xs font-normal text-gray-500">({usedPct}% of one NavIC segment)</span></p>
              <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
                <div className="bg-safe h-1.5 rounded-full" style={{ width: `${usedPct}%` }} />
              </div>
            </div>
            <button
              onClick={() => navigator.clipboard.writeText(capsuleBase32).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}
              className="w-full flex items-center gap-2 text-left font-mono text-[11px] bg-gray-50 border border-gray-200 rounded px-2 py-1 break-all hover:bg-gray-100"
              title="Copy base32 capsule"
            >
              {copied ? <CheckCircle2 className="w-3 h-3 text-safe shrink-0" /> : <Copy className="w-3 h-3 text-gray-400 shrink-0" />}
              {capsuleBase32}
            </button>
          </div>
        </div>
      )}

      {decodeError && <p className="text-xs text-danger">Capsule failed to decode: {decodeError}</p>}
      {spoken && (
        <div className="text-sm bg-gray-50 border border-gray-100 rounded p-2">
          <p className="text-[10px] font-semibold uppercase text-gray-500 mb-1">What the phone will say, decoded offline</p>
          <p lang={language} className="text-gray-800">{spoken.text}</p>
          {spoken.degraded && <p className="text-[10px] text-caution mt-1">Reason code degraded to the verdict's generic sentence.</p>}
        </div>
      )}
      <p className="text-[10px] text-gray-500">
        No transmitter exists in this build — the NavIC uplink is ISRO's. The same bytes hand off by QR, SMS or Bluetooth.
      </p>
    </section>
  );
}
