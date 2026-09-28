import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { Loader2, Mic, Satellite, Send, Square, TriangleAlert, X } from "lucide-react";
import { postAdvisory, type NearestPfz, type TraceStep } from "../shared/api/client";
import { decodeCapsule } from "../shared/capsule/decode";
import type { Capsule } from "../shared/capsule/decode";
import type { Language } from "../shared/capsule/codebook";
import {
  DEPARTURE_LABEL,
  QUESTIONS,
  departureTime,
  questionText,
  uplinkPayload,
  type Departure,
  type Question,
} from "../shared/questions";
import { startRecording, transcribe, type Recorder } from "../shared/voice";

/** The network half of Ask, kept out of the component so it is testable. */
export async function askAdvisory(
  query: string,
  lang: Language,
  boatClass: string,
  lat: number,
  lon: number,
  when?: string,
): Promise<AskResult> {
  const res = await postAdvisory({ query, lat, lon, language: lang, boat_class: boatClass, when });
  return {
    query,
    when,
    capsule: decodeCapsule(res.capsule_base32),
    narration: res.narration,
    riskClass: res.risk_class,
    capsuleBase32: res.capsule_base32,
    firewallPassed: res.firewall_passed,
    evidence: res.evidence,
    notice: res.notice,
    trace: res.trace ?? [],
    intent: res.intent ?? "",
    pfz: res.pfz ?? null,
    recordedAt: res.recorded_at ?? null,
  };
}

export interface AskResult {
  query: string;
  when?: string;
  capsule: Capsule;
  narration: string;
  riskClass: string;
  capsuleBase32: string;
  firewallPassed: boolean;
  evidence: Record<string, unknown>;
  notice: string;
  trace: TraceStep[];
  intent: string;
  pfz: NearestPfz | null;
  /** When the recorded run this answer replays was made; null for a live answer. */
  recordedAt: string | null;
}

interface Props {
  lat: number;
  lon: number;
  lang: Language;
  online: boolean;
  onAnswer: (result: AskResult) => void;
  onClose: () => void;
}

export function AskSheet({ lat, lon, lang, online, onAnswer, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [departure, setDeparture] = useState<Departure>("now");
  const [busy, setBusy] = useState<"idle" | "listening" | "hearing" | "asking">("idle");
  const [heard, setHeard] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uplink, setUplink] = useState<{ q: Question; svg: string } | null>(null);
  const recorder = useRef<Recorder | null>(null);

  useEffect(() => () => void recorder.current?.stop(), []);

  async function submit(text: string, when = departureTime(departure)) {
    const trimmed = text.trim();
    if (!trimmed || busy === "asking") return;
    setBusy("asking");
    setError(null);
    try {
      onAnswer(await askAdvisory(trimmed, lang, "frp_under_12m", lat, lon, when));
    } catch (err) {
      // Say what failed. A silent fallback to stale data is how a crew ends up
      // acting on yesterday's sea.
      setError(err instanceof Error ? err.message : "Could not reach the advisory service");
      setBusy("idle");
    }
  }

  async function toggleMic() {
    setError(null);
    if (busy === "listening" && recorder.current) {
      setBusy("hearing");
      try {
        const text = await transcribe(await recorder.current.stop(), lang);
        recorder.current = null;
        setHeard(text);
        setQuery(text);
        await submit(text);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not hear the question");
        setBusy("idle");
      }
      return;
    }
    try {
      recorder.current = await startRecording();
      setBusy("listening");
    } catch {
      setError("The microphone is not available. Allow it, or tap a question below.");
    }
  }

  async function sendBySatellite(q: Question) {
    const svg = await QRCode.toString(uplinkPayload(q.code, lang), { type: "svg", margin: 1 });
    setUplink({ q, svg });
  }

  const pick = (q: Question) => {
    if (!online) return void sendBySatellite(q);
    setQuery(questionText(q, lang));
    void submit(questionText(q, lang));
  };

  return (
    <div className="absolute inset-0 z-30 flex flex-col justify-end bg-ink/60">
      <button type="button" aria-label="Close" className="flex-1 w-full cursor-default" onClick={onClose} />

      <section className="bg-white rounded-t-3xl shadow-2xl max-h-[88%] flex flex-col">
        <header className="flex items-center justify-between px-5 pt-4 pb-1 shrink-0">
          <h2 className="text-2xl font-extrabold text-ink">
            {online ? "Ask about the sea" : "Ask by satellite"}
          </h2>
          <button onClick={onClose} aria-label="Close" className="w-12 h-12 -mr-2 flex items-center justify-center text-ink-soft">
            <X className="w-7 h-7" />
          </button>
        </header>

        {error && (
          <div className="mx-5 mb-3 flex items-start gap-3 rounded-xl border-2 border-danger bg-danger-light p-3">
            <TriangleAlert className="w-6 h-6 text-danger shrink-0" />
            <p className="text-sm font-semibold text-ink leading-snug">{error}</p>
          </div>
        )}

        {uplink ? (
          <div className="px-5 pb-6 flex flex-col items-center text-center">
            <p className="text-lg font-semibold text-ink">{questionText(uplink.q, lang)}</p>
            <div className="my-4 w-52 h-52 bg-white p-2 rounded-xl border-2 border-ink [&>svg]:w-full [&>svg]:h-full" dangerouslySetInnerHTML={{ __html: uplink.svg }} />
            <p className="text-base text-ink leading-snug max-w-xs">
              Show this to the boat terminal. It sends your question to shore as one byte.
            </p>
            <p className="text-sm text-ink-soft mt-1">
              Then tap Receive to read the answer. The Bluetooth link is simulated with a QR code.
            </p>
            <button onClick={() => setUplink(null)} className="mt-4 min-h-[52px] px-6 rounded-xl border-2 border-ink text-ink font-bold">
              Pick another question
            </button>
          </div>
        ) : (
          <div className="overflow-y-auto">
            {online ? (
              <div className="flex flex-col items-center px-5 pt-2 pb-4">
                <button
                  onClick={() => void toggleMic()}
                  disabled={busy === "hearing" || busy === "asking"}
                  aria-label={busy === "listening" ? "Stop and send" : "Ask by voice"}
                  className={`w-24 h-24 rounded-full flex items-center justify-center text-white shadow-lg disabled:opacity-60 ${
                    busy === "listening" ? "bg-danger listening" : "bg-sea"
                  }`}
                >
                  {busy === "listening" ? (
                    <Square className="w-9 h-9" fill="currentColor" />
                  ) : busy === "hearing" || busy === "asking" ? (
                    <Loader2 className="w-10 h-10 animate-spin" />
                  ) : (
                    <Mic className="w-11 h-11" />
                  )}
                </button>
                <p className="mt-3 text-base font-semibold text-ink" aria-live="polite">
                  {busy === "listening"
                    ? "Listening. Tap to send"
                    : busy === "hearing"
                      ? "Understanding your question"
                      : busy === "asking"
                        ? "Checking the sea for your boat"
                        : "Tap and speak your question"}
                </p>
                {heard && <p className="mt-1 text-sm text-ink-soft">Heard: “{heard}”</p>}
              </div>
            ) : (
              <p className="px-5 pb-3 text-base text-ink leading-snug">
                No mobile signal. Pick a question and the boat terminal sends it to shore over the
                satellite link.
              </p>
            )}

            {online && (
              <div className="px-5 pb-3">
                <p className="text-sm font-semibold text-ink-soft mb-2">Leaving</p>
                <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Departure time">
                  {(Object.keys(DEPARTURE_LABEL) as Departure[]).map((d) => (
                    <button
                      key={d}
                      role="radio"
                      aria-checked={departure === d}
                      onClick={() => setDeparture(d)}
                      className={`min-h-[48px] rounded-xl border-2 text-sm font-bold ${
                        departure === d ? "border-sea bg-sea text-white" : "border-rule text-ink"
                      }`}
                    >
                      {DEPARTURE_LABEL[d]}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="px-5 pb-3 flex flex-col gap-2">
              {QUESTIONS.map((q) => (
                <button
                  key={q.code}
                  disabled={busy !== "idle"}
                  onClick={() => pick(q)}
                  className="text-left w-full min-h-[56px] px-4 py-3 rounded-xl border-2 border-rule bg-mist text-ink font-semibold text-base leading-snug active:bg-rule disabled:opacity-40 flex items-center gap-3"
                >
                  {!online && <Satellite className="w-5 h-5 text-sea shrink-0" />}
                  <span>{questionText(q, lang)}</span>
                </button>
              ))}
            </div>

            {online && (
              <form
                className="p-5 pt-2 flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  void submit(query);
                }}
              >
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  disabled={busy !== "idle"}
                  placeholder="Or type a question"
                  aria-label="Your question"
                  className="flex-1 min-h-[56px] px-4 rounded-xl border-2 border-rule text-base text-ink placeholder:text-ink-soft focus:outline-none focus:border-sea disabled:bg-mist"
                />
                <button
                  type="submit"
                  disabled={busy !== "idle" || !query.trim()}
                  aria-label="Send question"
                  className="w-16 min-h-[56px] rounded-xl bg-sea text-white flex items-center justify-center disabled:bg-rule disabled:text-ink-soft"
                >
                  {busy === "asking" ? <Loader2 className="w-7 h-7 animate-spin" /> : <Send className="w-7 h-7" />}
                </button>
              </form>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
