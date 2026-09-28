import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { AlertTriangle, CheckCircle2, Copy, History, Loader2, MousePointerClick } from "lucide-react";
import demo from "../shared/demo.json";
import type { AdvisoryResponse, EvidenceBundle } from "../shared/api/client";
import { decodeCapsule } from "../shared/capsule/decode";
import { LANGUAGES, renderReason, type Language } from "../shared/capsule/codebook";
import { CAPSULE_BYTES, SEGMENT_BITS, TOTAL_BITS } from "../shared/capsule/fields";
import { verdictLabel, verdictState } from "../shared/verdict";
import { SIGN_THEME, VerdictSign } from "../boat/VerdictSign";
import { EvidenceList, TracePanel, advisoryDate, istTime } from "../boat/Explain";

export type InspectState =
  | { state: "idle" }
  | { state: "loading"; lat: number; lon: number; when: string | null }
  | { state: "error"; message: string }
  | { state: "ok"; lat: number; lon: number; when: string | null; boatClass: string; response: AdvisoryResponse };

export const BOAT_CLASSES = [
  ["frp_under_12m", "FRP or country craft, under 12 m"],
  ["mechanised_12_20m", "Mechanised, 12 to 20 m"],
  ["deep_sea_over_20m", "Deep-sea, over 20 m"],
] as const;

const LANGUAGE_NAMES: Record<Language, string> = {
  en: "English", ta: "Tamil", te: "Telugu", ml: "Malayalam", kn: "Kannada", mr: "Marathi",
  kok: "Konkani", gu: "Gujarati", or: "Odia", bn: "Bengali", hi: "Hindi", ur: "Urdu",
};

const VARIABLE_NAMES: Record<string, string> = {
  wave_height: "Wave height",
  wave_period: "Wave period",
  wind_speed: "Wind speed",
  wind_direction: "Wind direction",
  current_speed: "Current speed",
  current_direction: "Current direction",
  sst: "Sea temperature",
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
  /** Check the demo's real past rough day (shared/demo.json). */
  onReplayStorm?: () => void;
}

export function InspectPanel({ inspect, boatClass, onBoatClassChange, onReplayStorm }: Props) {
  if (inspect.state === "idle") {
    return (
      <div className="p-8 text-center text-ink-soft">
        <MousePointerClick className="w-10 h-10 mx-auto text-sea" />
        <p className="text-lg font-semibold text-ink mt-4">Click the sea to check a position</p>
        <p className="mt-2 leading-snug">
          DHRUVA runs the full check for that point, live, and shows what a boat there would be told.
        </p>
        {onReplayStorm && (
          <button
            onClick={onReplayStorm}
            className="mt-6 min-h-[48px] px-4 rounded-xl border-2 border-sea text-sea font-bold inline-flex items-center gap-2"
          >
            <History className="w-5 h-5" /> Replay a real storm: {demo.storm.name}, {advisoryDate(demo.storm.when)}
          </button>
        )}
        {onReplayStorm && (
          <p className="text-sm mt-2">Real archived waves and wind for that day, off Chennai.</p>
        )}
      </div>
    );
  }
  if (inspect.state === "loading") {
    return (
      <div className="p-8 flex items-center gap-3 text-ink">
        <Loader2 className="w-6 h-6 animate-spin text-sea" />
        Checking {inspect.lat.toFixed(3)}° N, {inspect.lon.toFixed(3)}° E
        {inspect.when ? ` as of ${utcStamp(inspect.when)}` : ""}
      </div>
    );
  }
  if (inspect.state === "error") {
    return (
      <div role="alert" className="m-4 p-4 rounded-xl border-2 border-danger bg-danger-light flex gap-3 text-ink font-semibold">
        <AlertTriangle className="w-6 h-6 text-danger shrink-0" />
        {inspect.message}
      </div>
    );
  }

  const { response, lat, lon, when } = inspect;
  const bundle = asBundle(response.evidence);
  const capsule = response.capsule_base32 ? decodeCapsule(response.capsule_base32) : null;
  const state = capsule ? verdictState(capsule) : "unavailable";
  const theme = SIGN_THEME[state];

  return (
    <div className="flex flex-col">
      <section className={`${theme.bg} ${theme.fg} px-5 py-4 flex items-center gap-4`}>
        <VerdictSign state={state} size={60} />
        <div className="min-w-0">
          <p className="text-3xl font-extrabold leading-none">{verdictLabel(state, "en").word}</p>
          <p className={`text-sm mt-1 ${theme.soft}`}>
            {lat.toFixed(3)}° N, {lon.toFixed(3)}° E
            {when ? `, conditions of ${utcStamp(when)}` : ", now"}
          </p>
        </div>
      </section>

      <div className="p-4 flex flex-col gap-4">
        {response.recorded_at && (
          <p className="rounded-xl bg-caution-light text-ink text-sm p-3 font-semibold">
            Replayed from a recorded live run of {istTime(response.recorded_at)}
            {response.replay_reason === "live sources failed" ? ", because the live sources did not answer" : ""}.
          </p>
        )}
        <label className="flex items-center justify-between gap-3 text-sm">
          <span className="text-ink-soft">Boat class</span>
          <select
            value={boatClass}
            onChange={(e) => onBoatClassChange(e.target.value)}
            className="border-2 border-rule rounded-lg px-2 py-1.5 bg-white text-ink"
          >
            {BOAT_CLASSES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>

        {capsule && <Spoken base32={response.capsule_base32} />}

        {bundle && bundle.items.length > 0 ? (
          <section>
            <h3 className="font-extrabold text-ink">The numbers behind it</h3>
            {capsule && <EvidenceList items={bundle.items} capsule={capsule} />}
            <p className="text-sm text-ink-soft">
              {response.firewall_passed
                ? "Number check passed: nothing is said that is not listed here."
                : "Number check failed, so the plain template was used."}
              {bundle.provisional_thresholds ? " Safety limits are provisional, not yet INCOIS criteria." : ""}
            </p>
          </section>
        ) : (
          <p className="text-ink-soft">No source answered for this position, so no figures are shown.</p>
        )}

        {response.trace && response.trace.length > 0 && (
          <section>
            <h3 className="font-extrabold text-ink">How it was worked out</h3>
            <TracePanel steps={response.trace} />
          </section>
        )}

        <CapsuleCard capsuleBase32={response.capsule_base32} />
        <p className="text-sm text-ink-soft">{response.notice}</p>
      </div>
    </div>
  );
}

function Spoken({ base32 }: { base32: string }) {
  const [language, setLanguage] = useState<Language>("ta");
  let text: string;
  try {
    text = renderReason(decodeCapsule(base32), language).text;
  } catch (err) {
    text = `Capsule failed to decode: ${err instanceof Error ? err.message : String(err)}`;
  }
  return (
    <section className="rounded-xl bg-mist p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-extrabold text-ink">What the boat will hear</h3>
        <select
          aria-label="Language"
          value={language}
          onChange={(e) => setLanguage(e.target.value as Language)}
          className="text-sm border-2 border-rule rounded-lg px-2 py-1 bg-white"
        >
          {LANGUAGES.map((l) => (
            <option key={l} value={l}>
              {LANGUAGE_NAMES[l]}
            </option>
          ))}
        </select>
      </div>
      <p lang={language} className="text-ink mt-2 leading-relaxed">
        {text}
      </p>
      <p className="text-xs text-ink-soft mt-2">Rebuilt from the capsule and the phone's phrasebook, with no network.</p>
    </section>
  );
}

function CapsuleCard({ capsuleBase32 }: { capsuleBase32: string }) {
  const [qrSvg, setQrSvg] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!capsuleBase32) return;
    let live = true;
    QRCode.toString(capsuleBase32, { type: "svg", margin: 1 }).then((svg) => live && setQrSvg(svg));
    return () => {
      live = false;
    };
  }, [capsuleBase32]);

  if (!capsuleBase32) return <p className="text-danger">The check returned no capsule for this position.</p>;
  return (
    <section className="flex gap-3 items-start">
      <div
        className="w-24 h-24 shrink-0 bg-white border-2 border-rule rounded-lg [&>svg]:w-full [&>svg]:h-full"
        aria-label="Capsule QR code"
        dangerouslySetInnerHTML={{ __html: qrSvg }}
      />
      <div className="min-w-0 flex-1">
        <h3 className="font-extrabold text-ink">The message</h3>
        <p className="text-sm text-ink-soft">
          {CAPSULE_BYTES} bytes, {TOTAL_BITS} of {SEGMENT_BITS} bits in one NavIC message.
        </p>
        <button
          onClick={() =>
            navigator.clipboard.writeText(capsuleBase32).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            })
          }
          className="mt-2 w-full flex items-center gap-2 text-left font-mono text-xs bg-mist rounded-lg px-2 py-1.5 break-all hover:bg-rule"
          title="Copy the capsule"
        >
          {copied ? <CheckCircle2 className="w-4 h-4 text-safe shrink-0" /> : <Copy className="w-4 h-4 text-ink-soft shrink-0" />}
          {capsuleBase32}
        </button>
      </div>
    </section>
  );
}
