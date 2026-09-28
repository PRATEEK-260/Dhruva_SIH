import { useCallback, useState } from "react";
import QRCode from "qrcode";
import { Camera, CloudLightning, History, Loader2, Radio, Satellite, Smartphone, Waves, X } from "lucide-react";
import { postAdvisory } from "../shared/api/client";
import { decodeBase32, decodeCapsule } from "../shared/capsule/decode";
import { FIELDS, SEGMENT_BITS, TOTAL_BITS, CAPSULE_BYTES } from "../shared/capsule/fields";
import type { Language } from "../shared/capsule/codebook";
import { QUESTIONS, departureTime, parseUplink, questionText, type Question } from "../shared/questions";
import { verdictLabel, verdictState, type VerdictState } from "../shared/verdict";
import { SIGN_THEME, VerdictSign } from "../boat/VerdictSign";
import { QrCamera } from "../shared/QrCamera";
import demo from "../shared/demo.json";
import { advisoryDate, istTime } from "../boat/Explain";

const DEFAULT_LAT = 11.05;
const DEFAULT_LON = 79.95;
// DAT-SG control-room text message, ICD v1.2: 23 bytes addressed to one terminal.
const DATSG_PAYLOAD_BYTES = 23;
const TEST_CYCLONE_KM = 180;

export async function generateHandoffQr(capsuleBase32: string): Promise<string> {
  return QRCode.toString(capsuleBase32, { type: "svg" });
}

// Field groups, coloured in the bit strip so a viewer can see what the 145 bits hold.
const GROUPS: { name: string; fields: string[]; color: string }[] = [
  { name: "Header and time", fields: ["msg_type", "schema_ver", "issue_slot", "valid_hours"], color: "#8aa1ab" },
  { name: "Position", fields: ["zone_id", "lat_offset", "lon_offset"], color: "#0e6178" },
  { name: "Verdict and hazards", fields: ["risk_class", "hazard_flags"], color: "#c62a1f" },
  { name: "Sea", fields: ["wave_hs", "wind_kt", "wind_dir", "curr_kt", "curr_dir", "sst"], color: "#2b8a9e" },
  { name: "Fishing zone", fields: ["chl_class", "pfz_bearing", "pfz_dist_nm", "pfz_conf"], color: "#0b7a4b" },
  { name: "Boundary", fields: ["bnd_dist_nm", "bnd_type", "bnd_eta_min"], color: "#e3a008" },
  { name: "Sentence code", fields: ["reason_code"], color: "#6e0d12" },
  { name: "Evidence fingerprint", fields: ["evidence_hash"], color: "#4a5f69" },
];

function bitColours(): string[] {
  const colourOf = new Map(GROUPS.flatMap((g) => g.fields.map((f) => [f, g.color] as const)));
  return FIELDS.flatMap((f) => Array<string>(f.width).fill(colourOf.get(f.name) ?? "#8aa1ab"));
}
const BIT_COLOURS = bitColours();

function bitsOf(base32: string): string {
  return [...decodeBase32(base32)]
    .map((b) => b.toString(2).padStart(8, "0"))
    .join("")
    .slice(0, TOTAL_BITS);
}

type Step = "idle" | "uplink" | "shore" | "downlink" | "ready";

interface Sent {
  kind: "answer" | "alert";
  title: string;
  base32: string;
  qr: string;
  state: VerdictState;
  lang: Language;
  recordedAt: string | null;
}

export function EmulatorApp() {
  const [lat, setLat] = useState(String(DEFAULT_LAT));
  const [lon, setLon] = useState(String(DEFAULT_LON));
  const [lang, setLang] = useState<Language>("ta");
  const [step, setStep] = useState<Step>("idle");
  const [scanning, setScanning] = useState(false);
  const [sent, setSent] = useState<Sent | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function transmit(
    kind: Sent["kind"],
    title: string,
    query: string,
    l: Language,
    extra: object,
    at?: { lat: number; lon: number },
  ) {
    const la = at?.lat ?? Number(lat);
    const lo = at?.lon ?? Number(lon);
    if (!Number.isFinite(la) || !Number.isFinite(lo)) return setError("Enter the boat's position as numbers.");
    setError(null);
    setSent(null);
    try {
      setStep("uplink");
      await new Promise((r) => setTimeout(r, 600));
      setStep("shore");
      const res = await postAdvisory({ query, lat: la, lon: lo, language: l, boat_class: "frp_under_12m", ...extra });
      setStep("downlink");
      await new Promise((r) => setTimeout(r, 600));
      const capsule = decodeCapsule(res.capsule_base32);
      setSent({
        kind,
        title,
        base32: res.capsule_base32,
        qr: await generateHandoffQr(res.capsule_base32),
        state: verdictState(capsule),
        lang: l,
        recordedAt: res.recorded_at ?? null,
      });
      setStep("ready");
    } catch {
      setStep("idle");
      setError("Shore did not answer. Check that the DHRUVA backend is running.");
    }
  }

  const ask = (q: Question, l: Language) =>
    transmit("answer", `Question ${q.code}: ${questionText(q, "en")}`, questionText(q, l), l, {
      when: departureTime(q.departure),
    });

  const alert = () =>
    transmit(
      "alert",
      `Shore alert: cyclone warning ${TEST_CYCLONE_KM} km away (test input)`,
      "Is there a cyclone warning?",
      lang,
      { test_cyclone_km: TEST_CYCLONE_KM, log: false },
    );

  // A real past rough day, replayed from the archives: the same check, for a
  // boat at the storm's position on that date.
  const storm = () => {
    const q = QUESTIONS.find((x) => x.code === 2)!;
    return transmit(
      "answer",
      `Replay: ${demo.storm.name}, ${advisoryDate(demo.storm.when)}, boat off Chennai`,
      questionText(q, lang),
      lang,
      { when: demo.storm.when },
      { lat: demo.storm.lat, lon: demo.storm.lon },
    );
  };

  const acceptUplink = useCallback(
    (text: string) => {
      const up = parseUplink(text);
      const q = up && QUESTIONS.find((x) => x.code === up.code);
      if (!up || !q) return false;
      setScanning(false);
      setLang(up.lang);
      void ask(q, up.lang);
      return true;
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lat, lon],
  );

  const busy = step === "uplink" || step === "shore" || step === "downlink";
  const bits = sent ? bitsOf(sent.base32) : "";

  return (
    <div className="min-h-dvh bg-ink text-white">
      {scanning && (
        <div className="fixed inset-0 z-50 bg-ink">
          <QrCamera accept={acceptUplink} hint="Show the phone's question code" />
          <button
            onClick={() => setScanning(false)}
            aria-label="Close"
            className="absolute top-4 right-4 w-14 h-14 rounded-full bg-white text-ink flex items-center justify-center"
          >
            <X className="w-7 h-7" />
          </button>
        </div>
      )}

      <header className="px-6 py-5 border-b border-white/15 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-4">
          <Radio className="w-10 h-10 text-caution" />
          <div>
            <h1 className="text-3xl font-extrabold leading-none">Boat terminal</h1>
            <p className="text-white/70 mt-1">
              Stands in for ISRO's DAT-SG on the boat. The satellite and Bluetooth links are simulated.
            </p>
          </div>
        </div>
        <div className="flex gap-3 text-sm">
          <label className="flex flex-col gap-1">
            <span className="text-white/60">Latitude</span>
            <input value={lat} onChange={(e) => setLat(e.target.value)} className="w-28 bg-white/10 border border-white/25 rounded-lg px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/60">Longitude</span>
            <input value={lon} onChange={(e) => setLon(e.target.value)} className="w-28 bg-white/10 border border-white/25 rounded-lg px-3 py-2" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/60">Language</span>
            <select value={lang} onChange={(e) => setLang(e.target.value as Language)} className="bg-white/10 border border-white/25 rounded-lg px-3 py-2">
              <option value="ta" className="text-ink">Tamil</option>
              <option value="ml" className="text-ink">Malayalam</option>
              <option value="or" className="text-ink">Odia</option>
              <option value="hi" className="text-ink">Hindi</option>
              <option value="en" className="text-ink">English</option>
            </select>
          </label>
        </div>
      </header>

      <main className="grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-6 p-6">
        <section className="flex flex-col gap-6">
          <div className="rounded-2xl bg-white/5 border border-white/15 p-5">
            <h2 className="text-xl font-extrabold">Question from the phone</h2>
            <p className="text-white/70 mt-1">
              The phone has no signal. It hands its question to this terminal, which sends it to shore
              as one byte.
            </p>
            <button
              onClick={() => setScanning(true)}
              disabled={busy}
              className="mt-4 w-full min-h-[56px] rounded-xl bg-sea font-bold text-lg flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <Camera className="w-6 h-6" /> Read the phone's question
            </button>
            <p className="text-sm text-white/60 mt-4 mb-2">Or send one from the keypad</p>
            <div className="flex flex-col gap-2">
              {QUESTIONS.map((q) => (
                <button
                  key={q.code}
                  disabled={busy}
                  onClick={() => void ask(q, lang)}
                  className="text-left min-h-[48px] px-4 rounded-xl border border-white/20 hover:bg-white/10 disabled:opacity-50 flex gap-3 items-center"
                >
                  <span className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center font-bold tabular-nums">{q.code}</span>
                  {questionText(q, lang)}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-2xl bg-white/5 border border-white/15 p-5">
            <h2 className="text-xl font-extrabold">Alert from shore</h2>
            <p className="text-white/70 mt-1">
              Shore works out what a warning means for this boat and sends it unasked. There is no live
              IMD feed yet, so the warning is a labelled test input.
            </p>
            <button
              onClick={() => void alert()}
              disabled={busy}
              className="mt-4 w-full min-h-[56px] rounded-xl bg-danger font-bold text-lg flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <CloudLightning className="w-6 h-6" /> Simulate a cyclone warning, {TEST_CYCLONE_KM} km
            </button>
            <button
              onClick={() => void storm()}
              disabled={busy}
              className="mt-3 w-full min-h-[52px] rounded-xl border-2 border-white/30 font-bold flex items-center justify-center gap-2 hover:bg-white/10 disabled:opacity-50"
            >
              <History className="w-5 h-5" /> Replay a real storm: {demo.storm.name}
            </button>
            <p className="text-sm text-white/60 mt-2">
              Real archived waves and wind from that day, not a test input.
            </p>
          </div>
          {error && <p className="rounded-xl bg-danger px-4 py-3 font-semibold">{error}</p>}
        </section>

        <section className="flex flex-col gap-6">
          <ol className="grid grid-cols-5 gap-2 text-center text-sm" aria-label="Link">
            {[
              { icon: Smartphone, label: "Phone", on: step !== "idle" },
              { icon: Satellite, label: "Up, 1 byte", on: step !== "idle" },
              { icon: Waves, label: "DHRUVA on shore", on: step === "shore" || step === "downlink" || step === "ready" },
              { icon: Satellite, label: `Down, ${CAPSULE_BYTES} bytes`, on: step === "downlink" || step === "ready" },
              { icon: Smartphone, label: "Phone speaks", on: step === "ready" },
            ].map((s, i) => (
              <li
                key={i}
                className={`rounded-xl py-3 px-1 border transition-colors ${s.on ? "bg-white text-ink border-white" : "border-white/20 text-white/50"}`}
              >
                <s.icon className="w-6 h-6 mx-auto" />
                <span className="block mt-1 font-semibold leading-tight">{s.label}</span>
              </li>
            ))}
          </ol>

          {busy && (
            <div className="rounded-2xl bg-white/5 border border-white/15 p-8 flex items-center gap-4 text-xl font-semibold">
              <Loader2 className="w-8 h-8 animate-spin" />
              {step === "uplink" ? "Sending to shore" : step === "shore" ? "DHRUVA is checking the sea for this boat" : "Receiving the answer"}
            </div>
          )}

          {sent && step === "ready" && (
            <div className="rounded-2xl bg-white text-ink p-5 grid md:grid-cols-[auto_minmax(0,1fr)] gap-6">
              <div className="flex flex-col items-center">
                <div className="w-60 h-60 [&>svg]:w-full [&>svg]:h-full" dangerouslySetInnerHTML={{ __html: sent.qr }} />
                <p className="text-sm text-ink-soft mt-2 text-center max-w-60">
                  On the phone, tap Receive. This QR stands in for Bluetooth.
                </p>
              </div>
              <div className="min-w-0">
                <p className="text-sm text-ink-soft">{sent.title}</p>
                {sent.recordedAt && (
                  <p className="text-sm font-semibold text-sea">
                    Replayed from a recorded live run of {istTime(sent.recordedAt)}.
                  </p>
                )}
                <div className={`mt-2 inline-flex items-center gap-3 rounded-xl px-3 py-2 ${SIGN_THEME[sent.state].bg} ${SIGN_THEME[sent.state].fg}`}>
                  <VerdictSign state={sent.state} size={40} />
                  <span className="text-2xl font-extrabold">{verdictLabel(sent.state, "en").word}</span>
                </div>

                <h3 className="text-lg font-extrabold mt-5">The whole answer, in {TOTAL_BITS} bits</h3>
                <div className="mt-2 grid gap-[2px]" style={{ gridTemplateColumns: "repeat(29, minmax(0, 1fr))" }} aria-label={`${TOTAL_BITS} bits`}>
                  {[...bits].map((b, i) => (
                    <span
                      key={i}
                      className="aspect-square rounded-[2px]"
                      style={{ background: BIT_COLOURS[i], opacity: b === "1" ? 1 : 0.28 }}
                    />
                  ))}
                </div>
                <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  {GROUPS.map((g) => (
                    <li key={g.name} className="flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded-sm" style={{ background: g.color }} />
                      {g.name}
                    </li>
                  ))}
                </ul>
                <p className="font-mono text-sm mt-3 break-all text-ink-soft">{sent.base32}</p>

                <dl className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl bg-mist p-3">
                    <dt className="text-sm text-ink-soft">DAT-SG text message to one boat</dt>
                    <dd className="text-xl font-extrabold">
                      {CAPSULE_BYTES} of {DATSG_PAYLOAD_BYTES} bytes
                    </dd>
                  </div>
                  <div className="rounded-xl bg-mist p-3">
                    <dt className="text-sm text-ink-soft">One NavIC message</dt>
                    <dd className="text-xl font-extrabold">
                      {TOTAL_BITS} of {SEGMENT_BITS} bits
                    </dd>
                  </div>
                </dl>
                <p className="text-sm text-ink-soft mt-3">
                  The phone rebuilds the spoken {sent.lang === "en" ? "English" : "regional-language"} answer
                  from these bits and its phrasebook, with no network.
                </p>
              </div>
            </div>
          )}

          {step === "idle" && !sent && (
            <div className="rounded-2xl border-2 border-dashed border-white/20 p-10 text-center text-white/60 text-lg">
              Waiting for a question from the phone or an alert from shore.
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
