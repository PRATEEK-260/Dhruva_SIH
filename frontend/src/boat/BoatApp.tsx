import { useCallback, useEffect, useMemo, useState } from "react";
import { Anchor, ChevronDown, ChevronUp, Fish, Loader2, MessageCircleQuestion, Navigation2, Satellite, ShieldAlert, Volume2, Wifi, WifiOff } from "lucide-react";
import { ScanView } from "./ScanView";
import { PfzMap } from "./PfzMap";
import { AskSheet, askAdvisory, type AskResult } from "./AskSheet";
import { VerdictSign, SIGN_THEME } from "./VerdictSign";
import { CapsuleFigures, EvidenceList, TracePanel, advisoryDate, hasFigures, istTime } from "./Explain";
import type { Capsule } from "../shared/capsule/decode";
import { compassWord, renderReason, spokenSlots, type Language } from "../shared/capsule/codebook";
import type { EvidenceItem, ImdStatus } from "../shared/api/client";
import { spokenAnswer, suppressesFishing, verdictLabel, verdictReason, verdictState, type VerdictState } from "../shared/verdict";
import { kmToNm, wayHome } from "../shared/harbour";
import { DEPARTURE_KEY, DEPARTURE_LABEL, departureTime, type Departure } from "../shared/questions";
import { speakAdvisory, type VoiceSource } from "../shared/voice";
import { t, type UiKey } from "../shared/i18n";

/** Which verdict banner a decoded capsule should show.
 *
 * risk_class decodes to fields.ts's lowercase-with-underscore form ("safe" |
 * "caution" | "no_go" | "unknown"), matching backend/dhruva/codec/fields.py
 * exactly, NOT uppercase display labels. Comparing against a display label was
 * the bug that once made NO-GO render no banner at all. */
export function verdictOf(
  riskClass: Capsule["risk_class"] | undefined,
): "no_go" | "caution" | "safe" | null {
  if (riskClass === "no_go" || riskClass === "caution" || riskClass === "safe") return riskClass;
  return null;
}

// 11.05N 79.95E is at sea, in the EEZ and territorial waters (docs/STATUS.md).
// The plan's original 11.05/79.85 is ashore, and Open-Meteo silently snaps a land
// request to a wet cell 11.9 km away, which is why nobody noticed.
const DEMO_LAT = 11.05;
const DEMO_LON = 79.95;

const LANG_OPTIONS: { code: Language; name: string }[] = [
  { code: "ta", name: "தமிழ்" },
  { code: "ml", name: "മലയാളം" },
  { code: "or", name: "ଓଡ଼ିଆ" },
  { code: "hi", name: "हिंदी" },
  { code: "en", name: "English" },
];

const VOICE_NOTE: Record<VoiceSource, UiKey> = {
  bhashini: "voice_bhashini",
  saved: "voice_saved",
  shipped: "voice_shipped",
  phone: "voice_phone",
  none: "voice_none",
};

/** What the voice says. The verdict's action line always comes first, so safety
 * leads; for query #7 the comparison follows, in the language it was asked in. */
function spokenText(s: Shown, lang: Language): string {
  const lines = s.asked?.decline?.lines?.length ? s.asked.decline.lines : s.asked?.answer?.lines;
  if (lines && lines.length > 0 && s.asked?.lang === lang) {
    const action = verdictLabel(verdictState(s.capsule), lang).line;
    return [action, ...lines.map((l) => l.text)].join(" ");
  }
  return spokenAnswer(s.capsule, lang);
}

interface Shown {
  capsule: Capsule;
  via: "online" | "satellite";
  at: Date;
  asked?: AskResult;
}

function useOnline(): boolean {
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}

export function BoatApp() {
  const [lang, setLang] = useState<Language>("ta");
  const online = useOnline();
  const [sheet, setSheet] = useState<"none" | "ask" | "scan">("none");
  const [shown, setShown] = useState<Shown | null>(null);
  const [voice, setVoice] = useState<VoiceSource | "speaking" | null>(null);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [compare, setCompare] = useState<{ d: Departure; state: VerdictState } | "loading" | null>(null);
  // Blocked and Unsafe repeat until the crew taps "I understand" (5-day plan).
  const [acknowledged, setAcknowledged] = useState(true);
  const [last, setLast] = useState<LastAnswer | null>(() => readLast());

  const state = shown ? verdictState(shown.capsule) : null;
  const sentence = useMemo(() => (shown ? renderReason(shown.capsule, lang) : null), [shown, lang]);
  const label = state ? verdictLabel(state, lang) : null;

  const say = useCallback(
    async (s: Shown, l: Language) => {
      const st = verdictState(s.capsule);
      setVoice("speaking");
      const text = spokenText(s, l);
      const source = await speakAdvisory({ text, lang: l, state: st, online: navigator.onLine });
      // null: a newer request took over, and it will set the label itself.
      if (source !== null) setVoice(source);
    },
    [],
  );

  const show = (s: Shown) => {
    setShown(s);
    setSheet("none");
    setCompare(null);
    setEvidenceOpen(false);
    const st = verdictState(s.capsule);
    setAcknowledged(!(st === "blocked" || st === "unsafe"));
    const entry: LastAnswer = { capsule: s.capsule, via: s.via, at: s.at.toISOString() };
    writeLast(entry);
    setLast(entry);
    void say(s, lang);
  };

  // Repeat a Blocked or Unsafe answer every 30 s until acknowledged, so a crew
  // that missed it the first time still hears it. Stops on a new answer.
  useEffect(() => {
    if (!shown || acknowledged) return;
    const id = window.setInterval(() => void say(shown, lang), REPEAT_MS);
    return () => window.clearInterval(id);
  }, [shown, acknowledged, lang, say]);

  const handleAnswer = (res: AskResult) => show({ capsule: res.capsule, via: "online", at: new Date(), asked: res });
  const handleScan = useCallback(
    (res: { capsule: Capsule }) => show({ capsule: res.capsule, via: "satellite", at: new Date() }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lang],
  );

  async function tryDeparture(d: Departure) {
    if (!shown?.asked) return;
    setCompare("loading");
    try {
      const res = await askAdvisory(shown.asked.query, lang, "frp_under_12m", DEMO_LAT, DEMO_LON, departureTime(d));
      setCompare({ d, state: verdictState(res.capsule) });
    } catch {
      setCompare(null);
    }
  }

  const theme = state ? SIGN_THEME[state] : null;
  const home = shown ? wayHome(shown.capsule.lat, shown.capsule.lon, lang) : null;
  const evidence = shown?.asked?.evidence as { items?: EvidenceItem[]; provisional_thresholds?: boolean } | undefined;
  const askedWhen = shown?.asked?.when;
  const currentDeparture: Departure | null = shown?.asked
    ? askedWhen === departureTime("tomorrow5")
      ? "tomorrow5"
      : askedWhen === departureTime("tomorrow7")
        ? "tomorrow7"
        : askedWhen
          ? null
          : "now"
    : null;

  return (
    <div className="bg-mist min-h-dvh max-w-md mx-auto flex flex-col relative text-ink">
      {sheet === "scan" && <ScanView lang={lang} onScan={handleScan} onClose={() => setSheet("none")} />}
      {sheet === "ask" && (
        <AskSheet lat={DEMO_LAT} lon={DEMO_LON} lang={lang} online={online} onAnswer={handleAnswer} onClose={() => setSheet("none")} />
      )}

      <header className="bg-ink text-white px-4 pt-3 pb-3 flex items-center justify-between gap-3 shrink-0">
        <div>
          <p className="text-2xl font-extrabold tracking-wide leading-none">DHRUVA</p>
          <p className="text-xs text-white/70 mt-1">{t("tagline", lang)}</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="sr-only" htmlFor="lang">
            Language
          </label>
          <select
            id="lang"
            value={lang}
            onChange={(e) => setLang(e.target.value as Language)}
            className="bg-white/10 text-white text-base px-2 py-2 rounded-lg border border-white/25"
          >
            {LANG_OPTIONS.map((o) => (
              <option key={o.code} value={o.code} className="text-ink">
                {o.name}
              </option>
            ))}
          </select>
          <span
            className={`flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-sm font-semibold ${
              online ? "bg-white/10 text-white" : "bg-caution text-ink"
            }`}
            role="status"
          >
            {online ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
            {online ? t("online", lang) : t("no_signal", lang)}
          </span>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto pb-28">
        {!shown || !state || !label || !theme || !sentence || !home ? (
          <section className="px-6 pt-16 text-center">
            <Anchor className="w-16 h-16 mx-auto text-sea" />
            <h1 className="text-3xl font-extrabold mt-5 leading-tight">{t("ask_before", lang)}</h1>
            <p className="text-lg text-ink-soft mt-3 leading-snug">{t("home_body", lang)}</p>
            <p className="text-base text-ink-soft mt-4 leading-snug">{t("home_offline", lang)}</p>
            {last && <LastAnswerCard last={last} lang={lang} onOpen={(s) => setShown(s)} />}
          </section>
        ) : (
          <>
            <section className={`${theme.bg} ${theme.fg} px-5 pt-6 pb-5`} aria-live="assertive">
              <div className="flex items-center gap-5 hoist" key={`${shown.at.getTime()}`}>
                <VerdictSign state={state} size={label.word.length > 11 ? 84 : 104} />
                <div className="min-w-0">
                  {/* Indic words are long; shrink rather than break one mid-word. */}
                  <h1
                    className={`font-extrabold leading-tight [overflow-wrap:normal] ${
                      label.word.length > 11 ? "text-2xl" : label.word.length > 6 ? "text-4xl" : "text-5xl"
                    }`}
                  >
                    {label.word}
                  </h1>
                  {lang !== "en" && <p className={`text-lg font-semibold mt-2 ${theme.soft}`}>{verdictLabel(state, "en").word}</p>}
                </div>
              </div>
              {/* Action first, then one reason with no numbers. The full sentence,
                  figures and all, is spoken, and written out under Show evidence. */}
              <p className="text-2xl font-extrabold mt-5 leading-snug">{label.line}</p>
              <p className={`text-lg mt-2 leading-snug ${theme.soft}`}>{verdictReason(shown.capsule, lang)}</p>

              <div className="mt-5 flex items-center gap-3">
                <button
                  onClick={() => void say(shown, lang)}
                  className={`min-h-[52px] px-5 rounded-xl font-bold flex items-center gap-2 whitespace-nowrap shrink-0 ${
                    state === "caution" ? "bg-ink text-white" : "bg-white text-ink"
                  }`}
                >
                  {voice === "speaking" ? <Loader2 className="w-6 h-6 animate-spin" /> : <Volume2 className="w-6 h-6" />}
                  {t("listen_again", lang)}
                </button>
                {voice && voice !== "speaking" && <p className={`text-sm ${theme.soft}`}>{t(VOICE_NOTE[voice], lang)}</p>}
              </div>
              {!acknowledged && (
                <button
                  onClick={() => setAcknowledged(true)}
                  className="mt-3 w-full min-h-[56px] rounded-xl bg-white text-ink font-extrabold text-lg"
                >
                  {t("understood", lang)}
                </button>
              )}

              <p className={`text-sm mt-4 ${theme.soft}`}>
                {shown.via === "satellite" ? t("arrived_satellite", lang) : t("answered_online", lang)}{" "}
                {shown.at.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}
                {askedWhen ? `, for leaving ${istTime(askedWhen)}` : ""}
                {shown.via === "satellite" ? ". Link simulated for this demo." : ""}
              </p>
              {shown.asked?.recordedAt && (
                <p className={`text-sm mt-1 font-semibold ${theme.soft}`}>
                  Replayed from a recorded live run of {istTime(shown.asked.recordedAt)}.
                </p>
              )}
            </section>

            <div className="px-4 pt-4 flex flex-col gap-4">
              {suppressesFishing(state) && (
                <div className="flex items-start gap-3 rounded-2xl bg-white border-2 border-danger p-4">
                  <ShieldAlert className="w-6 h-6 text-danger shrink-0" />
                  <p className="text-base font-semibold leading-snug">{t("fishing_hidden", lang)}</p>
                </div>
              )}

              <section className="rounded-2xl bg-white p-4">
                <div className="flex items-center gap-4">
                  <div
                    className="w-16 h-16 rounded-full bg-sea text-white flex items-center justify-center shrink-0"
                    aria-hidden
                  >
                    <Navigation2 className="w-8 h-8" style={{ transform: `rotate(${home.bearing}deg)` }} fill="currentColor" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm text-ink-soft">
                      {state === "unsafe" || state === "blocked" ? t("head_back", lang) : t("nearest_harbour", lang)}
                    </p>
                    <p className="text-xl font-extrabold leading-tight">{home.harbour.name}</p>
                    <p className="text-lg font-semibold">
                      {Math.round(kmToNm(home.km))} nm, {home.direction}
                    </p>
                  </div>
                </div>
                <p className="text-sm text-ink-soft mt-3">
                  {shown.via === "satellite"
                    ? `${t("worked_offline", lang)} `
                    : ""}
                  {t("straight_line", lang)}
                </p>
              </section>

              {shown.asked?.imd && <ImdCard imd={shown.asked.imd} lang={lang} />}

              {shown.asked?.decline && <DeclineCard shown={shown} lang={lang} />}

              {shown.asked?.answer && <AnswerCard shown={shown} lang={lang} />}

              {!suppressesFishing(state) && (
                <FishingZone shown={shown} lang={lang} />
              )}

              {shown.asked && online && currentDeparture && (shown.asked.intent === "go_no_go" || shown.asked.intent === "hazard") && (
                <section className="rounded-2xl bg-white p-4">
                  <h2 className="text-lg font-extrabold">{t("other_time", lang)}</h2>
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    {(Object.keys(DEPARTURE_LABEL) as Departure[]).map((d) => (
                      <button
                        key={d}
                        disabled={d === currentDeparture || compare === "loading"}
                        onClick={() => void tryDeparture(d)}
                        className={`min-h-[48px] rounded-xl border-2 text-sm font-bold ${
                          d === currentDeparture ? "border-ink bg-ink text-white" : "border-rule text-ink"
                        }`}
                      >
                        {t(DEPARTURE_KEY[d], lang)}
                      </button>
                    ))}
                  </div>
                  {compare === "loading" && <p className="mt-3 text-ink-soft">Checking that hour's forecast</p>}
                  {compare && compare !== "loading" && (
                    <div className="mt-3 flex items-center gap-3">
                      <div className={`${SIGN_THEME[compare.state].bg} rounded-lg p-1.5`}>
                        <VerdictSign state={compare.state} size={36} />
                      </div>
                      <p className="text-base font-semibold">
                        {t(DEPARTURE_KEY[compare.d], lang)}: {verdictLabel(compare.state, lang).word}
                        {compare.state === state ? `, ${t("same_as_now", lang)}` : ""}
                      </p>
                    </div>
                  )}
                </section>
              )}

              {/* Evidence stays one tap away: the answer first, the proof on request. */}
              <button
                onClick={() => setEvidenceOpen((o) => !o)}
                aria-expanded={evidenceOpen}
                aria-controls="evidence"
                className="min-h-[56px] rounded-2xl border-2 border-ink bg-white text-ink font-extrabold text-lg flex items-center justify-center gap-2"
              >
                {evidenceOpen ? <ChevronUp className="w-6 h-6" /> : <ChevronDown className="w-6 h-6" />}
                {evidenceOpen ? t("hide_evidence", lang) : t("show_evidence", lang)}
              </button>
              {evidenceOpen && (
                <div id="evidence" className="flex flex-col gap-4">
                  <section className="rounded-2xl bg-white p-4">
                    <h2 className="text-lg font-extrabold">{t("voice_says", lang)}</h2>
                    <p lang={lang} className="text-base mt-2 leading-relaxed">
                      {spokenText(shown, lang)}
                    </p>
                  </section>
                  {shown.asked && evidence?.items && evidence.items.length > 0 ? (
                    <section className="rounded-2xl bg-white p-4">
                      <h2 className="text-lg font-extrabold">{t("numbers_behind", lang)}</h2>
                      <p className="text-sm text-ink-soft">Every figure, with where and when it came from.</p>
                      <EvidenceList items={evidence.items} capsule={shown.capsule} lang={lang} />
                      <p className="text-sm text-ink-soft mt-1">
                        Number check {shown.asked.firewallPassed ? "passed" : "failed, so the plain template was used"}: the
                        answer contains no figure that is not listed here.
                        {evidence.provisional_thresholds ? " A limit used here is provisional, not yet an official criterion." : ""}
                      </p>
                    </section>
                  ) : !hasFigures(spokenSlots(shown.capsule, lang)) ? (
                    <p className="text-sm text-ink-soft px-1">
                      This message carries the warning itself and no sea figures. Full sources stay on shore
                      under evidence fingerprint {shown.capsule.evidence_hash.toString(16).padStart(3, "0")}.
                    </p>
                  ) : (
                    <section className="rounded-2xl bg-white p-4">
                      <h2 className="text-lg font-extrabold">Figures in this message</h2>
                      <p className="text-sm text-ink-soft mb-3">
                        Straight from the 145-bit message. Full sources stay on shore under fingerprint{" "}
                        {shown.capsule.evidence_hash.toString(16).padStart(3, "0")}.
                      </p>
                      <CapsuleFigures capsule={shown.capsule} slots={spokenSlots(shown.capsule, lang)} />
                    </section>
                  )}

                  {shown.asked && shown.asked.trace.length > 0 && (
                    <section className="rounded-2xl bg-white p-4">
                      <h2 className="text-lg font-extrabold">{t("how_worked", lang)}</h2>
                      <p className="text-sm text-ink-soft mb-2">
                        The problem statement's nine agents. Grey ones were not needed for this question.
                      </p>
                      <TracePanel steps={shown.asked.trace} />
                    </section>
                  )}
                </div>
              )}

              <p className="text-sm text-ink-soft px-1 pb-2">{t("advisory_only", lang)}</p>
            </div>
          </>
        )}
      </main>

      <nav className="fixed bottom-0 inset-x-0 max-w-md mx-auto bg-white border-t border-rule p-3 grid grid-cols-2 gap-3">
        <button
          onClick={() => setSheet("ask")}
          className="min-h-[64px] rounded-2xl bg-sea text-white flex items-center justify-center gap-2 text-lg font-extrabold"
        >
          <MessageCircleQuestion className="w-7 h-7" />
          {t("ask", lang)}
        </button>
        <button
          onClick={() => setSheet("scan")}
          className="min-h-[64px] rounded-2xl bg-ink text-white flex items-center justify-center gap-2 text-lg font-extrabold"
        >
          <Satellite className="w-7 h-7" />
          {t("receive", lang)}
        </button>
      </nav>
    </div>
  );
}

const FRESHNESS: Record<number, string> = {
  3: "issued within the last day",
  2: "issued within the last two days",
  1: "issued within the last three days",
};

/** The nearest INCOIS PFZ line. Online it names the advisory and its date;
 * from a satellite message it has only what the 145 bits carry. */
function FishingZone({ shown, lang }: { shown: Shown; lang: Language }) {
  const pfz = shown.asked?.pfz;
  const c = shown.capsule;
  const fishingAsked = shown.asked?.intent === "fishing_zone";
  if (!pfz && c.pfz_dist_nm === 0) {
    if (!fishingAsked) return null;
    return (
      <section className="rounded-2xl bg-white p-4 flex gap-4 items-start">
        <Fish className="w-8 h-8 text-ink-soft shrink-0" />
        <p className="text-base text-ink leading-snug">
          {t("no_pfz", lang)}
        </p>
      </section>
    );
  }
  const bearing = pfz ? pfz.bearing_deg : c.pfz_bearing_deg;
  return (
    <section className="rounded-2xl bg-white p-4">
      <div className="flex items-center gap-4">
        <div className="w-16 h-16 rounded-full bg-ink text-[#ffff00] flex items-center justify-center shrink-0" aria-hidden>
          <Navigation2 className="w-8 h-8" style={{ transform: `rotate(${bearing}deg)` }} fill="currentColor" />
        </div>
        <div className="min-w-0">
          <p className="text-sm text-ink-soft">{t("nearest_pfz", lang)}</p>
          <p className="text-xl font-extrabold leading-tight">
            {c.pfz_dist_nm} nm, {compassWord(c.pfz_bearing_deg, lang)}
          </p>
          {pfz ? (
            <p className="text-sm text-ink-soft">
              {t("incois_advisory", lang)} {advisoryDate(pfz.issued_for)}
              {pfz.basis ? `, from ${pfz.basis}` : ""}
            </p>
          ) : (
            <p className="text-sm text-ink-soft">INCOIS advisory, {FRESHNESS[c.pfz_conf] ?? "age unknown"}</p>
          )}
        </div>
      </div>
      <p className="text-sm text-ink-soft mt-3 leading-snug">
        {pfz?.centre_name ? `Off ${pfz.centre_name} landing centre. ` : ""}
        Distance to the nearest point of the line. Read from INCOIS's public PFZ map service
        {pfz ? "" : " and carried in the satellite message"}.
      </p>
      {pfz && typeof navigator !== "undefined" && navigator.onLine && (
        <PfzMap lat={c.lat} lon={c.lon} pfz={pfz} />
      )}
    </section>
  );
}

const DECLINE_PART: Record<string, UiKey> = {
  normal: "normal_here",
  changed: "what_changed",
  reason: "possible_reason",
  todo: "what_to_do",
};

/** Query #7: the last 30 days against the same weeks in earlier years. Online
 * only: the 145-bit message cannot carry a baseline, so there is no offline
 * version of this card. Every figure in it is an evidence row. */
function DeclineCard({ shown, lang }: { shown: Shown; lang: Language }) {
  const d = shown.asked?.decline;
  if (!d) return null;
  const caveat = d.lines.find((l) => l.part === "caveat");
  const body = d.lines.filter((l) => l.part !== "caveat");
  const sameLang = shown.asked?.lang === lang;
  return (
    <section className="rounded-2xl bg-white p-4">
      <div className="flex items-center gap-3">
        <Fish className="w-7 h-7 text-sea shrink-0" />
        <h2 className="text-lg font-extrabold leading-tight">{t("decline_title", lang)}</h2>
      </div>
      {body.length === 0 ? (
        <p className="text-base mt-3">The comparison could not be checked, so it is not shown.</p>
      ) : (
        <dl className="mt-3 flex flex-col gap-3">
          {body.map((l, i) => (
            <div key={i}>
              {(i === 0 || body[i - 1].part !== l.part) && (
                <dt className="text-sm font-semibold text-ink-soft">{DECLINE_PART[l.part] ? t(DECLINE_PART[l.part], lang) : l.part}</dt>
              )}
              <dd lang={shown.asked?.lang} className="text-base leading-snug">
                {l.text}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {caveat && (
        <p lang={shown.asked?.lang} className="text-sm font-semibold mt-3">
          {caveat.text}
        </p>
      )}
      <p className="text-sm text-ink-soft mt-2 leading-snug">
        {d.status === "ok"
          ? "Satellite data for a 20 km box around you, last 30 days against the same weeks in earlier years. "
          : ""}
        {sameLang ? "" : "Shown in the language it was asked in. "}
        Sources and dates are under Show evidence.
      </p>
    </section>
  );
}

/** Only an https link on IMD's own host is rendered: the URL comes from a
 * scraped page, and a javascript: URL in an href runs when tapped. */
function isImdLink(url: string | null): url is string {
  if (!url) return false;
  try {
    const u = new URL(url);
    return u.protocol === "https:" && u.hostname === "rsmcnewdelhi.imd.gov.in";
  } catch {
    return false;
  }
}

/** What IMD's cyclone bulletins in force say. With one in force: its fishermen
 * warning in IMD's own words and the link, whatever the verdict. With none:
 * one plain line with when the list was checked, never "no danger". */
function ImdCard({ imd, lang }: { imd: ImdStatus; lang: Language }) {
  if (imd.status !== "active") {
    // Built here from the check time, so it reads in the crew's language.
    if (imd.status === "unchecked" || !imd.checked_at) {
      return <p className="text-sm text-ink-soft px-1">{t("imd_unchecked", lang)}</p>;
    }
    const checked = new Date(imd.checked_at);
    const stale = Date.now() - checked.getTime() > 2 * 3600_000;
    return (
      <p className="text-sm text-ink-soft px-1">
        {t("no_imd_as_of", lang)}: {istTime(imd.checked_at)}.{stale ? ` ${t("imd_stale", lang)}` : ""}
      </p>
    );
  }
  return (
    <section className="rounded-2xl bg-white border-2 border-danger p-4">
      <div className="flex items-center gap-3">
        <ShieldAlert className="w-7 h-7 text-danger shrink-0" />
        <h2 className="text-lg font-extrabold leading-tight">{t("official_warning", lang)}</h2>
      </div>
      {imd.bulletins.map((b, i) => (
        <div key={i} className="mt-3">
          <p className="font-semibold">
            {b.name ? `${b.category} ${b.name}` : (b.category ?? "Cyclonic disturbance")}
            {b.system_id ? ` (${b.system_id})` : ""}
          </p>
          {b.fishermen_warning ? (
            <p className="text-base leading-snug mt-1">{b.fishermen_warning}</p>
          ) : (
            <p className="text-base leading-snug mt-1">
              DHRUVA could not read this bulletin, so it is treated as at least Caution. Read it before you go.
            </p>
          )}
          {isImdLink(b.source_url) && (
            <a href={b.source_url} target="_blank" rel="noopener" className="text-sea font-semibold underline text-sm">
              {b.title}, IMD RSMC New Delhi
            </a>
          )}
        </div>
      ))}
    </section>
  );
}

const ANSWER_TITLE: Record<string, UiKey> = {
  avoid: "title_avoid",
  thunder: "title_thunder",
  tide: "title_tide",
  productive: "title_productive",
  route: "title_route",
};

/** The answer to the brief's other example queries. Sentences picked by rule,
 * every figure an evidence row; online only, like query #7. */
function AnswerCard({ shown, lang }: { shown: Shown; lang: Language }) {
  const a = shown.asked?.answer;
  if (!a) return null;
  const caveat = a.lines.find((l) => l.part === "caveat");
  const body = a.lines.filter((l) => l.part !== "caveat");
  return (
    <section className="rounded-2xl bg-white p-4">
      <h2 className="text-lg font-extrabold leading-tight">{ANSWER_TITLE[a.kind] ? t(ANSWER_TITLE[a.kind], lang) : a.kind}</h2>
      {body.length === 0 ? (
        <p className="text-base mt-3">This answer could not be checked, so it is not shown.</p>
      ) : (
        <div className="mt-2 flex flex-col gap-2">
          {body.map((l, i) => (
            <p key={i} lang={a.language} className="text-base leading-snug">
              {l.text}
            </p>
          ))}
        </div>
      )}
      {caveat && (
        <p lang={a.language} className="text-sm font-semibold mt-3">
          {caveat.text}
        </p>
      )}
      <p className="text-sm text-ink-soft mt-2">
        {a.kind === "route" && a.line ? "The line is drawn on the fishing-zone map below. " : ""}
        Sources and times are under Show evidence.
      </p>
    </section>
  );
}

const REPEAT_MS = 30_000;
const LAST_KEY = "dhruva-last-answer";

/** The last answer this phone received, as its decoded 145-bit message: enough
 * to show the verdict again, offline, with no server. Kept in this phone's
 * storage only. */
interface LastAnswer {
  capsule: Capsule;
  via: "online" | "satellite";
  at: string;
}

function readLast(): LastAnswer | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? (JSON.parse(raw) as LastAnswer) : null;
  } catch {
    return null;
  }
}

function writeLast(entry: LastAnswer): void {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify(entry));
  } catch {
    // Storage blocked (private window): the home screen just has no last answer.
  }
}

function LastAnswerCard({
  last,
  lang,
  onOpen,
}: {
  last: LastAnswer;
  lang: Language;
  onOpen: (s: Shown) => void;
}) {
  const capsule = last.capsule;
  if (!capsule?.risk_class) return null;
  const st = verdictState(capsule);
  const theme = SIGN_THEME[st];
  const at = new Date(last.at);
  return (
    <button
      onClick={() => onOpen({ capsule, via: last.via, at })}
      className={`mt-8 w-full rounded-2xl ${theme.bg} ${theme.fg} p-4 flex items-center gap-4 text-left`}
    >
      <VerdictSign state={st} size={56} />
      <span className="min-w-0">
        <span className={`block text-sm ${theme.soft}`}>{t("last_answer", lang)}</span>
        <span className="block text-2xl font-extrabold leading-tight">{verdictLabel(st, lang).word}</span>
        <span className={`block text-sm ${theme.soft}`}>
          {at.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })}
        </span>
      </span>
    </button>
  );
}
