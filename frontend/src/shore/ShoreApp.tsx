import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ChevronRight, Loader2, RefreshCw, Ship, Smartphone, Radio } from "lucide-react";
import Map, {
  FullscreenControl, Layer, Marker, NavigationControl, Popup, ScaleControl, Source,
  type MapLayerMouseEvent, type MapRef,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import "../shared/map/maplibre";
import {
  fetchGeoLayer, fetchHealth, fetchRasterLayers, fetchRecentAdvisories, postAdvisory,
  type AdvisoryLogEntry, type GeoFeatureCollection, type RasterLayer,
} from "../shared/api/client";
import { ZONE_LAT_MAX, ZONE_LAT_MIN, ZONE_LON_MAX, ZONE_LON_MIN } from "../shared/capsule/fields";
import { InspectPanel, utcStamp, variableName, type InspectState } from "./InspectPanel";
import { ageLabel, displayStatus, filterRequests, inCapsuleGrid, type RequestFilter } from "./status";

export const RASTER_STYLE: Record<string, { rescale: [number, number]; colormap: string; gradient: string }> = {
  sst: { rescale: [18, 33], colormap: "thermal", gradient: "linear-gradient(90deg,#042333,#3e3891,#a65c85,#f9a242,#e8fa5b)" },
  chlorophyll: { rescale: [0, 5], colormap: "algae", gradient: "linear-gradient(90deg,#d7f9d0,#6fc16b,#1e7c38,#11361c)" },
  wave_height: { rescale: [0, 8], colormap: "blues", gradient: "linear-gradient(90deg,#f7fbff,#9ecae1,#4292c6,#08306b)" },
};

/** TiTiler's tilejson endpoint for one COG. MapLibre reads bounds and zoom
 * range from the response, which is less to get wrong than a hand-built
 * {z}/{x}/{y} template. */
export function tilejsonUrl(layer: RasterLayer): string {
  const style = RASTER_STYLE[layer.layer];
  const params = new URLSearchParams({
    url: `file:///data/cogs/${layer.file}`,
    rescale: style.rescale.join(","),
    colormap_name: style.colormap,
  });
  return `/tiles/cog/WebMercatorQuad/tilejson.json?${params.toString()}`;
}

type Load<T> = { state: "loading" } | { state: "ok"; data: T } | { state: "error"; message: string };

const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err));
const REFRESH_MS = 30_000;
const FILTERS: [RequestFilter, string][] = [["all", "All"], ["safe", "Safe"], ["caution", "Caution"], ["no_go", "No-Go"]];
const GO_NO_GO_QUERY = "Is it safe to go out at this position?";

export function ShoreApp() {
  const mapRef = useRef<MapRef>(null);
  const [health, setHealth] = useState<Load<null>>({ state: "loading" });
  const [boundaries, setBoundaries] = useState<Load<GeoFeatureCollection>>({ state: "loading" });
  const [pfz, setPfz] = useState<Load<GeoFeatureCollection>>({ state: "loading" });
  const [rasters, setRasters] = useState<Load<RasterLayer[]>>({ state: "loading" });
  const [requests, setRequests] = useState<Load<AdvisoryLogEntry[]>>({ state: "loading" });
  const [syncedAt, setSyncedAt] = useState<Date | null>(null);
  const [now, setNow] = useState(() => new Date());

  const [filter, setFilter] = useState<RequestFilter>("all");
  const [showPfz, setShowPfz] = useState(true);
  const [showBoundaries, setShowBoundaries] = useState(true);
  const [activeRaster, setActiveRaster] = useState<string | null>(null);
  const [rasterErrors, setRasterErrors] = useState<Record<string, string>>({});
  const [cursor, setCursor] = useState<{ lat: number; lon: number } | null>(null);
  const [pfzPopup, setPfzPopup] = useState<{ lat: number; lon: number; props: Record<string, unknown> } | null>(null);

  const [boatClass, setBoatClass] = useState("frp_under_12m");
  const [inspect, setInspect] = useState<InspectState>({ state: "idle" });
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const refreshRequests = useCallback(() => {
    fetchHealth()
      .then(() => setHealth({ state: "ok", data: null }))
      .catch((err) => setHealth({ state: "error", message: errorText(err) }));
    fetchRecentAdvisories(50)
      .then((data) => { setRequests({ state: "ok", data }); setSyncedAt(new Date()); })
      .catch((err) => setRequests({ state: "error", message: errorText(err) }));
  }, []);

  useEffect(() => {
    fetchGeoLayer("boundaries")
      .then((data) => setBoundaries({ state: "ok", data }))
      .catch((err) => setBoundaries({ state: "error", message: errorText(err) }));
    fetchGeoLayer("pfz")
      .then((data) => setPfz({ state: "ok", data }))
      .catch((err) => setPfz({ state: "error", message: errorText(err) }));
    fetchRasterLayers()
      .then((data) => setRasters({ state: "ok", data }))
      .catch((err) => setRasters({ state: "error", message: errorText(err) }));
    refreshRequests();
    const poll = setInterval(refreshRequests, REFRESH_MS);
    const tick = setInterval(() => setNow(new Date()), 15_000);
    return () => { clearInterval(poll); clearInterval(tick); };
  }, [refreshRequests]);

  const runInspect = useCallback(async (lat: number, lon: number, cls: string, when: string | null = null) => {
    if (!inCapsuleGrid(lat, lon)) {
      setInspect({
        state: "error",
        message: `Outside the capsule grid (${ZONE_LAT_MIN}–${ZONE_LAT_MAX}° N, ${ZONE_LON_MIN}–${ZONE_LON_MAX}° E) — no advisory can be encoded there.`,
      });
      return;
    }
    setInspect({ state: "loading", lat, lon, when });
    try {
      const response = await postAdvisory({ query: GO_NO_GO_QUERY, lat, lon, boat_class: cls, when: when ?? undefined, log: false });
      setInspect({ state: "ok", lat, lon, when, boatClass: cls, response });
    } catch (err) {
      setInspect({ state: "error", message: `Advisory failed: ${errorText(err)}` });
    }
  }, []);

  const inspectedPoint = inspect.state === "ok" || inspect.state === "loading" ? { lat: inspect.lat, lon: inspect.lon, when: inspect.when } : null;

  function handleBoatClassChange(cls: string) {
    setBoatClass(cls);
    if (inspectedPoint) runInspect(inspectedPoint.lat, inspectedPoint.lon, cls, inspectedPoint.when);
  }

  function handleMapClick(e: MapLayerMouseEvent) {
    const feature = e.features?.[0];
    if (feature && feature.layer.id === "pfz-points") {
      setPfzPopup({ lat: e.lngLat.lat, lon: e.lngLat.lng, props: feature.properties ?? {} });
      return;
    }
    setPfzPopup(null);
    setSelectedId(null);
    runInspect(e.lngLat.lat, e.lngLat.lng, boatClass);
  }

  function handleRequestClick(entry: AdvisoryLogEntry) {
    setSelectedId(entry.id);
    setPfzPopup(null);
    mapRef.current?.flyTo({ center: [entry.lon, entry.lat], zoom: Math.max(mapRef.current.getZoom(), 8) });
    const cls = entry.boat_class;
    setBoatClass(cls);
    runInspect(entry.lat, entry.lon, cls, entry.valid_for);
  }

  function handleMapError(e: { error?: Error; sourceId?: string }) {
    if (e.sourceId && e.sourceId.startsWith("raster-")) {
      const layer = e.sourceId.slice("raster-".length);
      setRasterErrors((prev) => (prev[layer] ? prev : { ...prev, [layer]: e.error?.message ?? "tile server error" }));
      return;
    }
    console.error("map error", e.error ?? e);
  }

  const rasterList = rasters.state === "ok" ? rasters.data : [];
  const active = rasterList.find((r) => r.layer === activeRaster) ?? null;
  const requestList = requests.state === "ok" ? filterRequests(requests.data, filter) : [];

  return (
    <div className="flex h-screen bg-gray-100 font-sans overflow-hidden text-gray-800">
      <aside className="w-14 lg:w-48 bg-dhruva-nav text-slate-300 flex flex-col shadow-xl z-20 shrink-0">
        <div className="h-16 flex items-center justify-center lg:justify-start lg:px-4 border-b border-slate-700/50">
          <Ship className="w-7 h-7 text-blue-400 shrink-0" />
          <span className="hidden lg:block ml-3 font-bold text-lg text-white tracking-wide">DHRUVA</span>
        </div>
        <nav className="flex-1 py-4 flex flex-col gap-1">
          <span className="flex items-center lg:px-4 py-3 mx-2 rounded-lg bg-blue-600 text-white">
            <Radio className="w-5 h-5 mx-auto lg:mx-0" /><span className="hidden lg:block ml-3 text-sm font-medium">Shore Console</span>
          </span>
          <Link to="/emulator" className="flex items-center lg:px-4 py-3 mx-2 rounded-lg hover:bg-slate-800 text-slate-400">
            <Smartphone className="w-5 h-5 mx-auto lg:mx-0" /><span className="hidden lg:block ml-3 text-sm font-medium">Boat (online)</span>
          </Link>
          <Link to="/boat" className="flex items-center lg:px-4 py-3 mx-2 rounded-lg hover:bg-slate-800 text-slate-400">
            <Ship className="w-5 h-5 mx-auto lg:mx-0" /><span className="hidden lg:block ml-3 text-sm font-medium">Boat (offline)</span>
          </Link>
        </nav>
      </aside>

      <div className="w-72 bg-white border-r border-gray-200 flex flex-col z-10 shadow-sm shrink-0">
        <div className="p-4 border-b border-gray-100">
          <div className="flex justify-between items-center">
            <h2 className="font-bold text-base">Advisory requests</h2>
            <button onClick={refreshRequests} title="Refresh now" className="p-1 rounded hover:bg-gray-100 text-gray-500">
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
          <p className="text-[11px] text-gray-500 mt-1 leading-snug">
            Where boats asked from, and the verdict they got. A request log — not live vessel positions.
          </p>
          <div className="flex gap-1.5 mt-3">
            {FILTERS.map(([value, label]) => {
              const count = requests.state === "ok" ? filterRequests(requests.data, value).length : null;
              return (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  aria-pressed={filter === value}
                  className={`px-2.5 py-1 rounded-full text-xs font-medium ${filter === value ? "bg-blue-600 text-white" : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"}`}
                >
                  {label}{count !== null && ` ${count}`}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {requests.state === "loading" && <p className="p-4 text-sm text-gray-400 flex gap-2"><Loader2 className="w-4 h-4 animate-spin" />Loading…</p>}
          {requests.state === "error" && <p role="alert" className="p-4 text-sm text-danger">Request log unavailable: {requests.message}</p>}
          {requests.state === "ok" && requestList.length === 0 && (
            <p className="p-4 text-sm text-gray-400">{requests.data.length === 0 ? "No boat has requested an advisory yet." : "No requests match this filter."}</p>
          )}
          {requestList.map((entry) => (
            <RequestItem key={entry.id} entry={entry} now={now} selected={entry.id === selectedId} onClick={() => handleRequestClick(entry)} />
          ))}
        </div>
      </div>

      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-5 shrink-0 gap-4">
          <div className="flex items-baseline gap-3 min-w-0">
            <h1 className="font-bold text-lg truncate">Maritime Operating Picture</h1>
            <span className="text-sm text-gray-500 hidden md:inline">ISRO PS 26176</span>
          </div>
          <div className="flex items-center gap-2 text-xs flex-wrap justify-end">
            <StatusChip label="API" load={health} />
            <StatusChip label="Boundaries" load={boundaries} count={boundaries.state === "ok" ? boundaries.data.features.length : undefined} />
            <StatusChip label="PFZ" load={pfz} count={pfz.state === "ok" ? pfz.data.features.length : undefined} />
            <StatusChip label="Rasters" load={rasters} count={rasters.state === "ok" ? rasters.data.length : undefined} />
            <span className="text-gray-500 ml-1">{syncedAt ? `Requests synced ${ageLabel(syncedAt, now)}` : "Not synced"}</span>
          </div>
        </header>

        <div className="flex-1 relative min-h-0 bg-slate-800">
          <Map
            ref={mapRef}
            initialViewState={{ longitude: 80.5, latitude: 12, zoom: 5.5 }}
            mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
            style={{ width: "100%", height: "100%" }}
            interactiveLayerIds={showPfz && pfz.state === "ok" ? ["pfz-points"] : []}
            onClick={handleMapClick}
            onMouseMove={(e) => setCursor({ lat: e.lngLat.lat, lon: e.lngLat.lng })}
            onMouseLeave={() => setCursor(null)}
            onError={handleMapError}
            cursor="crosshair"
          >
            <NavigationControl position="top-right" />
            <FullscreenControl position="top-right" />
            <ScaleControl position="bottom-right" unit="nautical" />

            {active && !rasterErrors[active.layer] && (
              <Source key={active.layer} id={`raster-${active.layer}`} type="raster" url={tilejsonUrl(active)} tileSize={512}>
                <Layer id={`raster-${active.layer}-layer`} type="raster" paint={{ "raster-opacity": 0.75 }} />
              </Source>
            )}
            {showBoundaries && boundaries.state === "ok" && (
              <Source id="boundaries" type="geojson" data={boundaries.data}>
                {/* Dashed: these lines are indicative, never legal (CLAUDE.md) */}
                <Layer id="boundaries-line" type="line" paint={{ "line-color": "#f59e0b", "line-width": 2, "line-dasharray": [2, 2] }} />
              </Source>
            )}
            {showPfz && pfz.state === "ok" && (
              <Source id="pfz" type="geojson" data={pfz.data}>
                <Layer id="pfz-points" type="circle" paint={{ "circle-radius": 6, "circle-color": "#22c55e", "circle-stroke-color": "#052e16", "circle-stroke-width": 1.5 }} />
              </Source>
            )}

            {requests.state === "ok" && requestList.map((entry) => {
              const status = displayStatus(entry.risk_class);
              return (
                <Marker key={entry.id} longitude={entry.lon} latitude={entry.lat} anchor="bottom"
                  onClick={(e) => { e.originalEvent.stopPropagation(); handleRequestClick(entry); }}>
                  <div title={`${status} · ${entry.boat_class}${entry.valid_for ? ` · replay of ${utcStamp(entry.valid_for)}` : ""}`}
                    className={`px-1 py-0.5 rounded-sm shadow-lg text-white text-[9px] font-bold cursor-pointer ${entry.id === selectedId ? "ring-2 ring-white" : ""} ${status === "NO-GO" ? "bg-danger" : status === "CAUTION" ? "bg-caution" : status === "SAFE" ? "bg-safe" : "bg-gray-500"}`}>
                    {status}
                  </div>
                </Marker>
              );
            })}

            {inspectedPoint && (
              <Marker longitude={inspectedPoint.lon} latitude={inspectedPoint.lat} anchor="center">
                <div className="w-4 h-4 rounded-full border-2 border-white bg-blue-500 shadow-[0_0_0_4px_rgba(59,130,246,0.35)]" />
              </Marker>
            )}

            {pfzPopup && (
              <Popup longitude={pfzPopup.lon} latitude={pfzPopup.lat} onClose={() => setPfzPopup(null)} closeOnClick={false} maxWidth="280px">
                <PfzDetails props={pfzPopup.props} />
              </Popup>
            )}
          </Map>

          <div className="absolute top-3 left-3 flex flex-col gap-2 z-10 max-w-[calc(100%-5rem)]">
            <div className="flex gap-1.5 flex-wrap">
              {(["sst", "chlorophyll", "wave_height"] as const).map((key) => {
                const available = rasterList.some((r) => r.layer === key);
                const failed = rasterErrors[key];
                return (
                  <LayerBtn
                    key={key}
                    label={variableName(key)}
                    active={activeRaster === key}
                    disabled={!available}
                    title={!available ? "Not generated — run python -m dhruva.geo.generate_cogs" : failed ? `Tile server error: ${failed}` : undefined}
                    onClick={() => setActiveRaster((cur) => (cur === key ? null : key))}
                  />
                );
              })}
              <LayerBtn label="PFZ" active={showPfz} disabled={pfz.state !== "ok"} onClick={() => setShowPfz((v) => !v)} />
              <LayerBtn label="Boundaries" active={showBoundaries} disabled={boundaries.state !== "ok"} onClick={() => setShowBoundaries((v) => !v)} />
            </div>
            {active && <RasterLegend layer={active} error={rasterErrors[active.layer]} />}
          </div>

          <div className="absolute bottom-3 left-3 z-10 flex flex-col gap-1.5 items-start">
            {showBoundaries && boundaries.state === "ok" && boundaries.data.features.length > 0 && (
              <span className="bg-black/75 text-white text-[10px] px-2.5 py-1 rounded flex items-center gap-2">
                <span className="inline-block w-5 border-t-2 border-dashed border-amber-500" />
                Boundaries are indicative only, not a legal line.
              </span>
            )}
            <span className="bg-black/75 text-white text-xs px-2.5 py-1 rounded font-mono">
              {cursor ? `${cursor.lat.toFixed(3)}° N  ${cursor.lon.toFixed(3)}° E` : "Hover the map for position"}
            </span>
          </div>
        </div>

        <div className="h-72 bg-gray-50 border-t border-gray-200 p-3 shrink-0 overflow-y-auto">
          <InspectPanel inspect={inspect} boatClass={boatClass} onBoatClassChange={handleBoatClassChange} />
        </div>
      </main>
    </div>
  );
}

function RequestItem({ entry, now, selected, onClick }: { entry: AdvisoryLogEntry; now: Date; selected: boolean; onClick: () => void }) {
  const status = displayStatus(entry.risk_class);
  const tone = status === "SAFE" ? "bg-safe" : status === "CAUTION" ? "bg-caution" : status === "NO-GO" ? "bg-danger" : "bg-gray-500";
  return (
    <button onClick={onClick} className={`w-full text-left p-3 border-b border-gray-100 flex gap-3 items-start relative ${selected ? "bg-blue-50" : "hover:bg-gray-50"}`}>
      {selected && <span className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500" />}
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-start gap-2 mb-0.5">
          <span className="font-semibold text-sm text-gray-800 truncate">{entry.boat_class.replace(/_/g, " ")}</span>
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold tracking-wider text-white ${tone}`}>{status}</span>
        </div>
        <p className="text-xs text-gray-500 font-mono">{entry.lat.toFixed(3)}° N, {entry.lon.toFixed(3)}° E</p>
        <p className="text-[10px] text-gray-400" title={entry.issued_at}>{ageLabel(new Date(entry.issued_at), now)}</p>
        {entry.valid_for && (
          <p className="text-[10px] font-semibold text-slate-600 mt-0.5">Replay · conditions of {utcStamp(entry.valid_for)}</p>
        )}
      </div>
      <ChevronRight className="w-4 h-4 text-gray-300 mt-1 shrink-0" />
    </button>
  );
}

function StatusChip({ label, load, count }: { label: string; load: Load<unknown>; count?: number }) {
  if (load.state === "loading") {
    return <span className="px-2 py-1 rounded bg-gray-100 text-gray-500 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />{label}</span>;
  }
  if (load.state === "error") {
    return (
      <span role="alert" title={load.message} className="px-2 py-1 rounded bg-danger-light text-danger font-semibold flex items-center gap-1">
        <AlertTriangle className="w-3 h-3" />{label} down
      </span>
    );
  }
  return (
    <span className="px-2 py-1 rounded bg-safe-light text-green-800 font-medium flex items-center gap-1">
      <span className="w-1.5 h-1.5 rounded-full bg-safe" />{label}{count !== undefined && ` · ${count}`}
    </span>
  );
}

function LayerBtn({ label, active, disabled, title, onClick }: { label: string; active: boolean; disabled?: boolean; title?: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      title={title}
      className={`px-3 py-1.5 rounded shadow text-xs font-medium backdrop-blur-sm ${
        disabled ? "bg-slate-900/50 text-slate-500 cursor-not-allowed line-through" :
        active ? "bg-blue-600 text-white" : "bg-slate-900/75 text-white hover:bg-slate-900/90"
      }`}
    >
      {label}
    </button>
  );
}

function RasterLegend({ layer, error }: { layer: RasterLayer; error?: string }) {
  const style = RASTER_STYLE[layer.layer];
  return (
    <div className="bg-black/80 text-white text-[10px] rounded px-2.5 py-2 w-64 space-y-1">
      {error ? (
        <p className="text-red-300 font-semibold">Tiles failed to load: {error}</p>
      ) : (
        <>
          <div className="h-2 rounded" style={{ background: style.gradient }} />
          <div className="flex justify-between font-mono"><span>{style.rescale[0]}</span><span>{layer.unit || "colour scale"}</span><span>{style.rescale[1]}</span></div>
        </>
      )}
      <p className="font-mono break-all text-slate-300">{layer.dataset_id} · {layer.variable}</p>
      <p className="text-slate-300">Valid {utcStamp(layer.valid_time)} · generated {utcStamp(layer.generated_at)}</p>
    </div>
  );
}

function PfzDetails({ props }: { props: Record<string, unknown> }) {
  const text = (key: string) => (props[key] == null || props[key] === "" ? null : String(props[key]));
  const url = text("source_url");
  return (
    <div className="text-xs text-gray-800 space-y-0.5">
      <p className="font-bold text-sm">Potential Fishing Zone</p>
      {text("landing_centre") && <p>Landing centre: {text("landing_centre")}</p>}
      {text("region") && <p>Region: {text("region")}</p>}
      {text("bearing_deg") && text("distance_nm") && <p>{text("distance_nm")} nm at {text("bearing_deg")}° from the landing centre</p>}
      {text("depth_m") && <p>Depth: {text("depth_m")} m</p>}
      <p className="text-gray-500 pt-1">
        Scraped from {text("source_name") ?? "INCOIS bulletin"}, fetched {utcStamp(text("fetched_at"))}.{" "}
        {url && <a href={url} target="_blank" rel="noreferrer" className="text-blue-600 underline">Source</a>}
      </p>
    </div>
  );
}
