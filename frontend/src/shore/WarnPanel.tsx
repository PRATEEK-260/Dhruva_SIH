import { useState } from "react";
import { CloudLightning, Loader2, MapPin, Send } from "lucide-react";
import { postAdvisory } from "../shared/api/client";
import { decodeCapsule } from "../shared/capsule/decode";
import { CAPSULE_BYTES } from "../shared/capsule/fields";
import { distanceKm } from "../shared/harbour";
import { verdictLabel, verdictState, type VerdictState } from "../shared/verdict";
import { SIGN_THEME, VerdictSign } from "../boat/VerdictSign";

/** The absolute override radius (CLAUDE.md, docs/THRESHOLDS.md): a cyclone warning
 * within this distance is NO-GO for every boat class. Drawn on the map; the
 * verdict itself still comes from the backend's rule table. */
export const CYCLONE_RADIUS_KM = 300;

export interface Boat {
  lat: number;
  lon: number;
  /** Set for a labelled demo boat (backend dhruva/demo/boats.py), not a vessel. */
  name?: string;
}

type Result =
  | { boat: Boat; km: number; status: "waiting" | "working" }
  | { boat: Boat; km: number; status: "error"; message: string }
  | { boat: Boat; km: number; status: "ok"; state: VerdictState; base32: string; recordedAt: string | null };

export function boatKey(b: Boat): string {
  return `${b.lat.toFixed(3)},${b.lon.toFixed(3)}`;
}

export function WarnPanel({
  centre,
  boats,
  onVerdict,
  onPlaceDemo,
}: {
  centre: Boat | null;
  boats: Boat[];
  /** Put the cyclone at the demo position (shared/demo.json). */
  onPlaceDemo: () => void;
  /** Each boat's verdict under this warning, so the map can show it. */
  onVerdict: (boat: Boat, state: VerdictState) => void;
}) {
  const [results, setResults] = useState<Result[]>([]);
  const [running, setRunning] = useState(false);

  async function run() {
    if (!centre) return;
    const initial: Result[] = boats
      .map((boat) => ({ boat, km: distanceKm(centre.lat, centre.lon, boat.lat, boat.lon), status: "waiting" as const }))
      .sort((a, b) => a.km - b.km);
    setResults(initial);
    setRunning(true);
    // One at a time: each check calls the planner model, which is rate-limited.
    for (let i = 0; i < initial.length; i++) {
      const { boat, km } = initial[i];
      setResults((rs) => rs.map((r, j) => (j === i ? { boat, km, status: "working" } : r)));
      try {
        const res = await postAdvisory({
          query: "Is there a cyclone warning?",
          lat: boat.lat,
          lon: boat.lon,
          language: "ta",
          test_cyclone_km: Math.round(km),
          log: false,
        });
        const state = verdictState(decodeCapsule(res.capsule_base32));
        onVerdict(boat, state);
        const recordedAt = res.recorded_at ?? null;
        setResults((rs) =>
          rs.map((r, j) => (j === i ? { boat, km, status: "ok", state, base32: res.capsule_base32, recordedAt } : r)),
        );
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setResults((rs) => rs.map((r, j) => (j === i ? { boat, km, status: "error", message } : r)));
      }
    }
    setRunning(false);
  }

  const done = results.filter((r): r is Extract<Result, { status: "ok" }> => r.status === "ok");
  const distinct = new Set(done.map((r) => r.base32)).size;

  return (
    <div className="p-4 flex flex-col gap-4">
      <div className="flex gap-3">
        <CloudLightning className="w-8 h-8 text-danger shrink-0" />
        <div>
          <h2 className="text-xl font-extrabold text-ink leading-tight">One warning, a message for each boat</h2>
          <p className="text-ink-soft mt-1 leading-snug">
            A broadcast tells every boat the same thing. Here shore works out what the warning means for
            each boat and sends each its own {CAPSULE_BYTES}-byte message.
          </p>
        </div>
      </div>

      <p className="rounded-xl bg-caution-light text-ink text-sm p-3 leading-snug">
        Test input. No live IMD cyclone feed is connected yet, so the warning is placed by hand. Boats
        are the positions in the request log and {boats.filter((b) => b.name).length} labelled demo
        boats on real fishing grounds; the demo boats are not vessels.
      </p>

      {!centre ? (
        <div className="rounded-xl border-2 border-dashed border-rule p-5 text-center text-ink-soft">
          <MapPin className="w-7 h-7 mx-auto text-danger" />
          <p className="mt-2 font-semibold text-ink">Click the map to place the cyclone</p>
          <p className="text-sm">
            The red ring shows {CYCLONE_RADIUS_KM} km, the distance at which a warning means no boat goes out.
          </p>
          <button
            onClick={onPlaceDemo}
            className="mt-3 min-h-[44px] px-4 rounded-xl border-2 border-danger text-danger font-bold"
          >
            Use the demo cyclone position
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-ink">
            Cyclone at <strong>{centre.lat.toFixed(2)}° N, {centre.lon.toFixed(2)}° E</strong>.{" "}
            {boats.length} boat{boats.length === 1 ? "" : "s"} known.
          </p>
          <button
            onClick={() => void run()}
            disabled={running || boats.length === 0}
            className="min-h-[52px] rounded-xl bg-danger text-white font-extrabold text-lg flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {running ? <Loader2 className="w-6 h-6 animate-spin" /> : <Send className="w-6 h-6" />}
            {running ? "Working out each boat's message" : "Work out each boat's message"}
          </button>
        </div>
      )}

      {results.length > 0 && (
        <ul className="flex flex-col gap-2">
          {results.map((r, i) => (
            <li key={i} className="rounded-xl bg-white border-2 border-rule p-3 flex items-center gap-3">
              {r.status === "ok" ? (
                <div className={`${SIGN_THEME[r.state].bg} rounded-lg p-1.5 shrink-0`}>
                  <VerdictSign state={r.state} size={32} />
                </div>
              ) : (
                <div className="w-11 h-11 rounded-lg bg-mist flex items-center justify-center shrink-0">
                  {r.status === "working" && <Loader2 className="w-5 h-5 animate-spin text-sea" />}
                </div>
              )}
              <div className="min-w-0 flex-1">
                <p className="font-extrabold text-ink">
                  {r.status === "ok" ? verdictLabel(r.state, "en").word : r.status === "error" ? "Failed" : "Waiting"}
                  <span className="font-semibold text-ink-soft">
                    , {Math.round(r.km)} km from the cyclone
                  </span>
                </p>
                <p className="text-sm text-ink-soft">
                  {r.boat.name ? `Demo boat ${r.boat.name}` : `Boat at ${r.boat.lat.toFixed(3)}° N, ${r.boat.lon.toFixed(3)}° E`}
                  {r.status === "ok" && r.recordedAt ? ", recorded run" : ""}
                </p>
                {r.status === "ok" && <p className="font-mono text-xs text-ink-soft break-all">{r.base32}</p>}
                {r.status === "error" && <p className="text-sm text-danger">{r.message}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}

      {!running && done.length > 0 && (
        <p className="text-ink font-semibold">
          {done.length} boat{done.length === 1 ? "" : "s"}, {distinct} different message{distinct === 1 ? "" : "s"}.
          Each goes to one terminal as a DAT-SG text message; the phone speaks it in the crew's language.
        </p>
      )}
    </div>
  );
}
