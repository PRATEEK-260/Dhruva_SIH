import { useEffect, useRef, useState } from "react";
import { Send, X, Loader2, WifiOff, TriangleAlert } from "lucide-react";
import { postAdvisory } from "../shared/api/client";
import { decodeCapsule } from "../shared/capsule/decode";
import type { Capsule } from "../shared/capsule/decode";
import type { Language } from "../shared/capsule/codebook";

/** Answering a typed question needs the network.
 *
 * The plan's offline envelope is explicit that the app must say plainly what it
 * cannot answer without a link rather than guessing, so this sheet refuses up
 * front when offline instead of firing a fetch that will hang on a boat with no
 * signal. The scanned-capsule path is what works out there; this is the onshore
 * path, and conflating the two is what would make the offline claim dishonest.
 */

/** The network half of Ask, kept out of the component so it is testable.
 *
 * This is the function BoatApp.test.ts used to cover before the boat/emulator
 * split deleted it; the coverage moved here rather than being dropped.
 */
export async function askAdvisory(
  query: string,
  lang: Language,
  boatClass: string,
  lat: number,
  lon: number,
): Promise<AskResult> {
  const res = await postAdvisory({ query, lat, lon, language: lang, boat_class: boatClass });
  return {
    capsule: decodeCapsule(res.capsule_base32),
    narration: res.narration,
    riskClass: res.risk_class,
    capsuleBase32: res.capsule_base32,
    firewallPassed: res.firewall_passed,
    evidence: res.evidence,
    notice: res.notice,
  };
}

export interface AskResult {
  capsule: Capsule;
  narration: string;
  riskClass: string;
  capsuleBase32: string;
  firewallPassed: boolean;
  evidence: Record<string, unknown>;
  notice: string;
}

interface Props {
  lat: number;
  lon: number;
  lang: Language;
  online: boolean;
  onAnswer: (result: AskResult) => void;
  onClose: () => void;
}

/** Starter questions, one per PS question type the router handles.
 *
 * Typing on a wet deck with one hand on the tiller is the thing the interface
 * constraints exist to avoid, so the common questions are one tap. They are
 * also what the eval set routes on, which keeps the demo honest — these are
 * queries the classifier is measured against, not ones picked to flatter it.
 */
const SUGGESTIONS: Record<string, string[]> = {
  en: [
    "Can I go out to sea this morning?",
    "Where is the nearest fishing zone?",
    "How far am I from the border?",
    "Is there a cyclone warning?",
  ],
  ta: [
    "இன்று காலை கடலுக்குப் போகலாமா?",
    "மீன் பிடிக்க எங்கே போவது?",
    "எல்லைக்கு எவ்வளவு தூரம்?",
    "புயல் எச்சரிக்கை உள்ளதா?",
  ],
  hi: [
    "क्या मैं आज समुद्र में जा सकता हूँ?",
    "आज मछली कहाँ मिलेगी?",
    "सीमा से कितनी दूर हूँ?",
    "क्या कोई तूफान की चेतावनी है?",
  ],
};

export function AskSheet({ lat, lon, lang, online, onAnswer, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const suggestions = SUGGESTIONS[lang] ?? SUGGESTIONS.en;

  async function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      // Render the answer through the same capsule the offline path uses, so an
      // asked advisory and a scanned one cannot disagree on screen.
      onAnswer(await askAdvisory(trimmed, lang, "frp_under_12m", lat, lon));
    } catch (err) {
      // Say what failed. A silent fallback to stale data is how a crew ends up
      // acting on yesterday's sea.
      setError(err instanceof Error ? err.message : "Could not reach the advisory service");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="absolute inset-0 z-30 flex flex-col justify-end bg-black/60">
      <button
        type="button"
        aria-label="Dismiss"
        className="flex-1 w-full cursor-default"
        onClick={onClose}
      />

      <section className="bg-white rounded-t-2xl shadow-2xl max-h-[85%] flex flex-col">
        <header className="flex items-center justify-between px-4 pt-4 pb-2 shrink-0">
          <h2 className="text-xl font-bold text-gray-900">Ask</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="w-14 h-14 -mr-2 flex items-center justify-center text-gray-600 active:text-gray-900"
          >
            <X className="w-7 h-7" />
          </button>
        </header>

        {!online && (
          <div className="mx-4 mb-3 flex items-start gap-3 rounded-xl border-2 border-amber-600 bg-amber-50 p-3">
            <WifiOff className="w-6 h-6 text-amber-700 shrink-0 mt-0.5" />
            <p className="text-sm font-semibold text-amber-900 leading-snug">
              No network. A new question needs a link — scan a QR instead to read the
              last advisory sent for your zone.
            </p>
          </div>
        )}

        {error && (
          <div className="mx-4 mb-3 flex items-start gap-3 rounded-xl border-2 border-red-600 bg-red-50 p-3">
            <TriangleAlert className="w-6 h-6 text-red-700 shrink-0 mt-0.5" />
            <p className="text-sm font-semibold text-red-900 leading-snug">{error}</p>
          </div>
        )}

        <div className="px-4 pb-2 overflow-y-auto">
          <p className="text-xs font-bold uppercase tracking-wider text-gray-500 mb-2">
            Common questions
          </p>
          <div className="flex flex-col gap-2">
            {suggestions.map((s) => (
              <button
                key={s}
                disabled={!online || busy}
                onClick={() => {
                  setQuery(s);
                  void submit(s);
                }}
                className="text-left w-full min-h-[56px] px-4 py-3 rounded-xl border-2 border-gray-300
                           bg-gray-50 text-gray-900 font-semibold text-base leading-snug
                           active:bg-gray-200 disabled:opacity-40"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <form
          className="p-4 pt-3 border-t border-gray-200 flex gap-2 shrink-0"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(query);
          }}
        >
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={!online || busy}
            placeholder={online ? "Type your question…" : "Offline — scan a QR instead"}
            aria-label="Your question"
            className="flex-1 min-h-[56px] px-4 rounded-xl border-2 border-gray-400 text-base
                       text-gray-900 placeholder:text-gray-500 focus:outline-none
                       focus:border-blue-600 disabled:bg-gray-100"
          />
          <button
            type="submit"
            disabled={!online || busy || !query.trim()}
            aria-label="Send question"
            className="w-16 min-h-[56px] rounded-xl bg-blue-600 text-white flex items-center
                       justify-center active:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-500"
          >
            {busy ? <Loader2 className="w-7 h-7 animate-spin" /> : <Send className="w-7 h-7" />}
          </button>
        </form>
      </section>
    </div>
  );
}
