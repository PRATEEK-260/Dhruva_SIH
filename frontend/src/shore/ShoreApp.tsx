import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, CloudLightning, ListChecks, Loader2, Radio, RefreshCw, Ship, Smartphone, Crosshair } from "lucide-react";
import demo from "../shared/demo.json";
import Map, {
  FullscreenControl, Layer, Marker, NavigationControl, Popup, ScaleControl, Source,
  type MapLayerMouseEvent, type MapRef,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import "../shared/map/maplibre";
import { BASEMAPS, type BasemapId } from "../shared/map/basemaps";
import { BOUNDARY_MAGENTA, PFZ_CASING, PFZ_YELLOW } from "../shared/map/colours";
import {
  fetchDemoBoats, fetchGeoLayer, fetchHealth, fetchRasterLayers, fetchRecentAdvisories, postAdvisory,
  type AdvisoryLogEntry, type DemoBoat, type GeoFeatureCollection, type RasterLayer,
} from "../shared/api/client";
import { ZONE_LAT_MAX, ZONE_LAT_MIN, ZONE_LON_MAX, ZONE_LON_MIN } from "../shared/capsule/fields";
import { circleRing } from "../shared/harbour";
import { verdictState, type VerdictState } from "../shared/verdict";
import { SIGN_THEME, VerdictSign } from "../boat/VerdictSign";
import { sourceName } from "../boat/Explain";
import { InspectPanel, utcStamp, variableName, type InspectState } from "./InspectPanel";
import { WarnPanel, CYCLONE_RADIUS_KM, boatKey, type Boat, type Cyclone } from "./WarnPanel";
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
type Tab = "check" | "warn" | "requests";

const errorText = (err: unknown) => (err instanceof Error ? err.message : String(err));
const REFRESH_MS = 30_000;
const FILTERS: [RequestFilter, string][] = [["all", "All"], ["safe", "Safe"], ["caution", "Caution"], ["no_go", "No-go"]];
const GO_NO_GO_QUERY = "Is it safe to go out at this position?";

/** The request log carries risk_class only, not hazards, so a logged no-go
 * shows as Unsafe; it cannot say whether a warning caused it. */
function logState(riskClass: string): VerdictState {
  return verdictState({ risk_class: riskClass, hazards: [] });
}

export function ShoreApp() {
  const mapRef = useRef<MapRef>(null);
  const [health, setHealth] = useState<Load<null>>({ state: "loading" });
  const [boundaries, setBoundaries] = useState<Load<GeoFeatureCollection>>({ state: "loading" });
  const [pfz, setPfz] = useState<Load<GeoFeatureCollection>>({ state: "loading" });
  const [rasters, setRasters] = useState<Load<RasterLayer[]>>({ state: "loading" });
  const [requests, setRequests] = useState<Load<AdvisoryLogEntry[]>>({ state: "loading" });
  const [syncedAt, setSyncedAt] = useState<Date | null>(null);
  const [now, setNow] = useState(() => new Date());

  const [tab, setTab] = useState<Tab>("check");
  const [filter, setFilter] = useState<RequestFilter>("all");
  // INCOIS's latest PFZ lines, read from its public geoportal WFS.
  const [showPfz, setShowPfz] = useState(true);
  const [showBoundaries, setShowBoundaries] = useState(true);
  const [basemap, setBasemap] = useState<BasemapId>("seafloor");
  const [activeRaster, setActiveRaster] = useState<string | null>(null);
  const [rasterErrors, setRasterErrors] = useState<Record<string, string>>({});
  const [cursor, setCursor] = useState<{ lat: number; lon: number } | null>(null);
  const [pfzPopup, setPfzPopup] = useState<{ lat: number; lon: number; props: Record<string, unknown> } | null>(null);

  const [boatClass, setBoatClass] = useState("frp_under_12m");
  const [inspect, setInspect] = useState<InspectState>({ state: "idle" });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [cyclone, setCyclone] = useState<Cyclone | null>(null);
  const [demoBoats, setDemoBoats] = useState<DemoBoat[]>([]);
  // Verdicts under the placed warning, shown on the map while Warn boats is open.
  const [warned, setWarned] = useState<Record<string, VerdictState>>({});

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
    fetchDemoBoats().then(setDemoBoats).catch(() => setDemoBoats([]));
    refreshRequests();
    const poll = setInterval(refreshRequests, REFRESH_MS);
    const tick = setInterval(() => setNow(new Date()), 15_000);
    return () => { clearInterval(poll); clearInterval(tick); };
  }, [refreshRequests]);

  const runInspect = useCallback(async (lat: number, lon: number, cls: string, when: string | null = null) => {
    if (!inCapsuleGrid(lat, lon)) {
      setInspect({
        state: "error",
        message: `That point is outside the area a message can address (${ZONE_LAT_MIN}–${ZONE_LAT_MAX}° N, ${ZONE_LON_MIN}–${ZONE_LON_MAX}° E).`,
      });
      return;
    }
    setInspect({ state: "loading", lat, lon, when });
    try {
      // The replayed storm's hour carries IMD's bulletin, so the check sees the
      // cyclone as the terminal's replay does, not waves and wind alone.
      const bulletin = when === demo.storm.when ? demo.storm.bulletin : undefined;
      const response = await postAdvisory({ query: GO_NO_GO_QUERY, lat, lon, boat_class: cls, when: when ?? undefined, bulletin, log: false });
      setInspect({ state: "ok", lat, lon, when, boatClass: cls, response });
    } catch (err) {
      setInspect({ state: "error", message: `The check failed: ${errorText(err)}` });
    }
  }, []);

  const inspectedPoint = inspect.state === "ok" || inspect.state === "loading" ? { lat: inspect.lat, lon: inspect.lon, when: inspect.when } : null;

  function handleBoatClassChange(cls: string) {
    setBoatClass(cls);
    if (inspectedPoint) runInspect(inspectedPoint.lat, inspectedPoint.lon, cls, inspectedPoint.when);
  }

  function handleMapClick(e: MapLayerMouseEvent) {
    const feature = e.features?.[0];
    if (feature && feature.layer.id === "pfz-hit") {
      setPfzPopup({ lat: e.lngLat.lat, lon: e.lngLat.lng, props: feature.properties ?? {} });
      return;
    }
    setPfzPopup(null);
    if (tab === "warn") {
      setCyclone({ lat: e.lngLat.lat, lon: e.lngLat.lng });
      setWarned({});
      return;
    }
    setSelectedId(null);
    setTab("check");
    runInspect(e.lngLat.lat, e.lngLat.lng, boatClass);
  }

  function handleRequestClick(entry: AdvisoryLogEntry) {
    setSelectedId(entry.id);
    setPfzPopup(null);
    setTab("check");
    mapRef.current?.flyTo({ center: [entry.lon, entry.lat], zoom: Math.max(mapRef.current.getZoom(), 7) });
    setBoatClass(entry.boat_class);
    runInspect(entry.lat, entry.lon, entry.boat_class, entry.valid_for);
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
  const pfzIssued = pfz.state === "ok" ? (pfz.data.features[0]?.properties?.issued_for as string | undefined) : undefined;
  const pfzDate = pfzIssued ? new Date(pfzIssued).toLocaleDateString("en-IN", { timeZone: "UTC", day: "numeric", month: "short" }) : null;
  const active = rasterList.find((r) => r.layer === activeRaster) ?? null;
  const allRequests = useMemo(() => (requests.state === "ok" ? requests.data : []), [requests]);
  const requestList = filterRequests(allRequests, filter);

  // One marker per position: the latest request there. The log is newest first.
  const latestByPosition = useMemo(() => {
    const seen = new Set<string>();
    return allRequests.filter((e) => {
      const key = `${e.lat.toFixed(3)},${e.lon.toFixed(3)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [allRequests]);
  // Request-log positions, then the labelled demo boats, one per position.
  const boats: Boat[] = useMemo(() => {
    const seen = new Set<string>();
    const all: Boat[] = [
      ...latestByPosition.map((e) => ({ lat: e.lat, lon: e.lon })),
      ...demoBoats.map((b) => ({ lat: b.lat, lon: b.lon, name: b.name })),
    ];
    return all.filter((b) => {
      const k = boatKey(b);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  }, [latestByPosition, demoBoats]);

  function placeDemoCyclone() {
    setCyclone({ lat: demo.cyclone.lat, lon: demo.cyclone.lon });
    setWarned({});
    mapRef.current?.flyTo({ center: [80.8, 11.3], zoom: 5.2 });
  }

  function placeStorm() {
    const c = demo.storm.imd_centre;
    setCyclone({
      lat: c.lat,
      lon: c.lon,
      replay: { when: demo.storm.when, bulletin: demo.storm.bulletin, label: demo.storm.bulletin_label },
    });
    setWarned({});
    mapRef.current?.flyTo({ center: [80.8, 11.3], zoom: 5.2 });
  }

  function replayStorm() {
    setSelectedId(null);
    setTab("check");
    mapRef.current?.flyTo({ center: [demo.storm.lon, demo.storm.lat], zoom: 7 });
    runInspect(demo.storm.lat, demo.storm.lon, boatClass, demo.storm.when);
  }

  const cycloneRing = useMemo(
    () =>
      cyclone && {
        type: "Feature" as const,
        properties: {},
        geometry: { type: "Polygon" as const, coordinates: [circleRing(cyclone.lat, cyclone.lon, CYCLONE_RADIUS_KM)] },
      },
    [cyclone],
  );

  return (
    <div className="flex flex-col h-dvh bg-mist text-ink overflow-hidden">
      <header className="bg-ink text-white h-16 px-5 flex items-center justify-between gap-4 shrink-0">
        <div className="flex items-center gap-6 min-w-0">
          <Link to="/" className="text-2xl font-extrabold tracking-wide">DHRUVA</Link>
          <span className="text-white/70 hidden md:inline">Shore console</span>
          <nav className="flex gap-1 text-sm">
            <Link to="/boat" className="flex items-center gap-1.5 px-3 py-2 rounded-lg hover:bg-white/10"><Smartphone className="w-4 h-4" />Phone</Link>
            <Link to="/emulator" className="flex items-center gap-1.5 px-3 py-2 rounded-lg hover:bg-white/10"><Radio className="w-4 h-4" />Boat terminal</Link>
          </nav>
        </div>
        <div className="flex items-center gap-2 text-sm flex-wrap justify-end">
          <Health label="Backend" load={health} />
          <Health label="Boundaries" load={boundaries} count={boundaries.state === "ok" ? boundaries.data.features.length : undefined} />
          <Health label="Satellite layers" load={rasters} count={rasters.state === "ok" ? rasters.data.length : undefined} />
          <button onClick={refreshRequests} title="Refresh the request log" className="p-2 rounded-lg hover:bg-white/10">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 relative min-w-0 bg-ink">
          <Map
            ref={mapRef}
            initialViewState={{ longitude: 79.5, latitude: 11.5, zoom: 5.4 }}
            mapStyle={BASEMAPS[basemap].style}
            style={{ width: "100%", height: "100%" }}
            interactiveLayerIds={showPfz && pfz.state === "ok" ? ["pfz-hit"] : []}
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
                <Layer id="boundaries-line" type="line" paint={{ "line-color": BOUNDARY_MAGENTA, "line-width": 1.8, "line-dasharray": [2, 2] }} />
              </Source>
            )}
            {showPfz && pfz.state === "ok" && (
              <Source id="pfz" type="geojson" data={pfz.data}>
                <Layer id="pfz-casing" type="line" paint={{ "line-color": PFZ_CASING, "line-width": 5.5 }} />
                <Layer id="pfz-line" type="line" paint={{ "line-color": PFZ_YELLOW, "line-width": 2.8 }} />
                {/* Wide and invisible, so a thin line is easy to click. */}
                <Layer id="pfz-hit" type="line" paint={{ "line-color": "#000000", "line-width": 16, "line-opacity": 0 }} />
              </Source>
            )}
            {cycloneRing && (
              <Source id="cyclone" type="geojson" data={cycloneRing}>
                <Layer id="cyclone-fill" type="fill" paint={{ "fill-color": "#c62a1f", "fill-opacity": 0.14 }} />
                <Layer id="cyclone-line" type="line" paint={{ "line-color": "#c62a1f", "line-width": 2 }} />
              </Source>
            )}
            {cyclone && (
              <Marker longitude={cyclone.lon} latitude={cyclone.lat} anchor="center">
                <div className="w-9 h-9 rounded-full bg-danger text-white flex items-center justify-center shadow-lg">
                  <CloudLightning className="w-5 h-5" />
                </div>
              </Marker>
            )}

            {latestByPosition.map((entry) => {
              const state = (tab === "warn" && warned[boatKey(entry)]) || logState(entry.risk_class);
              return (
                <Marker key={entry.id} longitude={entry.lon} latitude={entry.lat} anchor="center"
                  onClick={(e) => { e.originalEvent.stopPropagation(); handleRequestClick(entry); }}>
                  <button
                    title={`${displayStatus(entry.risk_class)}, asked ${ageLabel(new Date(entry.issued_at), now)}`}
                    className={`${SIGN_THEME[state].bg} rounded-lg p-1 shadow-lg ${entry.id === selectedId ? "ring-3 ring-white" : ""}`}
                  >
                    <VerdictSign state={state} size={22} />
                  </button>
                </Marker>
              );
            })}

            {tab === "warn" &&
              demoBoats.map((b) => {
                const st = warned[boatKey(b)];
                return (
                  <Marker key={`demo-${b.name}`} longitude={b.lon} latitude={b.lat} anchor="center">
                    <div
                      title={`Demo boat ${b.name}`}
                      className={`rounded-lg p-1 shadow-lg ${st ? SIGN_THEME[st].bg : "bg-ink"} ring-2 ring-white/70`}
                    >
                      {st ? <VerdictSign state={st} size={20} /> : <Ship className="w-5 h-5 text-white" />}
                    </div>
                  </Marker>
                );
              })}

            {tab === "check" && inspect.state === "ok" && inspect.response.pfz && (
              <>
                <Source
                  id="to-pfz"
                  type="geojson"
                  data={{
                    type: "Feature",
                    properties: {},
                    geometry: {
                      type: "LineString",
                      coordinates: [[inspect.lon, inspect.lat], [inspect.response.pfz.lon, inspect.response.pfz.lat]],
                    },
                  }}
                >
                  <Layer id="to-pfz-line" type="line" paint={{ "line-color": "#0f2a36", "line-width": 2.5, "line-dasharray": [2, 1.5] }} />
                </Source>
                <Marker longitude={inspect.response.pfz.lon} latitude={inspect.response.pfz.lat} anchor="left">
                  <div className="flex items-center gap-1.5 -ml-2">
                    <span className="w-4 h-4 rounded-full border-[3px] border-ink shadow" style={{ background: PFZ_YELLOW }} />
                    <span className="bg-white text-ink text-xs font-bold px-2 py-1 rounded-md shadow">
                      Nearest potential fishing zone, {Math.round(inspect.response.pfz.distance_nm * 10) / 10} nm
                    </span>
                  </div>
                </Marker>
              </>
            )}

            {inspectedPoint && tab === "check" && (
              <Marker longitude={inspectedPoint.lon} latitude={inspectedPoint.lat} anchor="center">
                <div className="w-5 h-5 rounded-full border-[3px] border-white bg-sea shadow-[0_0_0_5px_rgb(14_97_120/0.4)]" />
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
                    title={!available ? "Not generated: run python -m dhruva.geo.generate_cogs" : failed ? `Tile server error: ${failed}` : undefined}
                    onClick={() => setActiveRaster((cur) => (cur === key ? null : key))}
                  />
                );
              })}
              <LayerBtn label="Boundaries" active={showBoundaries} disabled={boundaries.state !== "ok"} onClick={() => setShowBoundaries((v) => !v)} />
              <LayerBtn
                label={pfzDate ? `Potential fishing zones, INCOIS ${pfzDate}` : "Potential fishing zones"}
                active={showPfz}
                disabled={pfz.state !== "ok" || pfz.data.features.length === 0}
                title={pfz.state === "ok" && pfz.data.features.length === 0 ? "No fresh INCOIS advisory loaded" : undefined}
                onClick={() => setShowPfz((v) => !v)}
              />
            </div>
            <div className="flex rounded-lg shadow overflow-hidden self-start" role="radiogroup" aria-label="Base map">
              {(Object.keys(BASEMAPS) as BasemapId[]).map((id) => (
                <button
                  key={id}
                  role="radio"
                  aria-checked={basemap === id}
                  onClick={() => setBasemap(id)}
                  className={`px-3 py-2 text-sm font-semibold ${basemap === id ? "bg-sea text-white" : "bg-ink/85 text-white hover:bg-ink"}`}
                >
                  {BASEMAPS[id].label}
                </button>
              ))}
            </div>
            {active && <RasterLegend layer={active} error={rasterErrors[active.layer]} />}
          </div>

          <div className="absolute bottom-3 left-3 z-10 flex flex-col gap-1.5 items-start">
            {tab === "warn" && (
              <span className="bg-danger text-white text-sm font-semibold px-3 py-1.5 rounded-lg flex items-center gap-2">
                <Crosshair className="w-4 h-4" /> Click the map to place the cyclone (test input)
              </span>
            )}
            {showPfz && pfz.state === "ok" && pfz.data.features.length > 0 && (
              <span className="bg-ink/85 text-white text-xs px-3 py-1.5 rounded-lg flex items-center gap-2 max-w-md">
                <span className="inline-block w-5 h-1 rounded-sm shrink-0" style={{ background: PFZ_YELLOW }} />
                Potential fishing zones, INCOIS{pfzDate ? ` ${pfzDate}` : ""}: where satellite data suggests fish may gather. Not a safety signal.
              </span>
            )}
            {showBoundaries && boundaries.state === "ok" && boundaries.data.features.length > 0 && (
              <span className="bg-ink/85 text-white text-xs px-3 py-1.5 rounded-lg flex items-center gap-2">
                <span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: BOUNDARY_MAGENTA }} />
                Boundaries are indicative only, not a legal line.
              </span>
            )}
            <span className="bg-ink/85 text-white text-xs px-3 py-1.5 rounded-lg tabular-nums">
              {cursor ? `${cursor.lat.toFixed(3)}° N, ${cursor.lon.toFixed(3)}° E` : "Point at the map for a position"}
            </span>
          </div>
        </div>

        <aside className="w-[440px] shrink-0 bg-white border-l border-rule flex flex-col min-h-0">
          <div className="grid grid-cols-3 border-b border-rule shrink-0" role="tablist">
            <TabBtn active={tab === "check"} onClick={() => setTab("check")} icon={<Crosshair className="w-4 h-4" />} label="Check a point" />
            <TabBtn active={tab === "warn"} onClick={() => setTab("warn")} icon={<CloudLightning className="w-4 h-4" />} label="Warn boats" />
            <TabBtn
              active={tab === "requests"}
              onClick={() => setTab("requests")}
              icon={<ListChecks className="w-4 h-4" />}
              label={`Requests${requests.state === "ok" ? ` ${requests.data.length}` : ""}`}
            />
          </div>
          <div className="flex-1 overflow-y-auto">
            {tab === "check" && (
              <InspectPanel
                inspect={inspect}
                boatClass={boatClass}
                onBoatClassChange={handleBoatClassChange}
                onReplayStorm={replayStorm}
              />
            )}
            {tab === "warn" && (
              <WarnPanel
                centre={cyclone}
                boats={boats}
                onPlaceDemo={placeDemoCyclone}
                onPlaceStorm={placeStorm}
                onVerdict={(b, st) => setWarned((w) => ({ ...w, [boatKey(b)]: st }))}
              />
            )}
            {tab === "requests" && (
              <div>
                <div className="p-4 border-b border-rule">
                  <p className="text-sm text-ink-soft leading-snug">
                    Where boats asked from and the verdict they got. A request log, not live vessel tracking.
                    {syncedAt ? ` Updated ${ageLabel(syncedAt, now)}.` : ""}
                  </p>
                  <div className="flex gap-1.5 mt-3">
                    {FILTERS.map(([value, label]) => (
                      <button
                        key={value}
                        onClick={() => setFilter(value)}
                        aria-pressed={filter === value}
                        className={`px-3 py-1.5 rounded-lg text-sm font-semibold border-2 ${filter === value ? "bg-ink text-white border-ink" : "border-rule text-ink"}`}
                      >
                        {label} {filterRequests(allRequests, value).length}
                      </button>
                    ))}
                  </div>
                </div>
                {requests.state === "loading" && <p className="p-4 text-ink-soft flex gap-2"><Loader2 className="w-5 h-5 animate-spin" />Loading</p>}
                {requests.state === "error" && <p role="alert" className="p-4 text-danger">Request log unavailable: {requests.message}</p>}
                {requests.state === "ok" && requestList.length === 0 && (
                  <p className="p-4 text-ink-soft">{allRequests.length === 0 ? "No boat has asked yet." : "No requests match this filter."}</p>
                )}
                <ul>
                  {requestList.map((entry) => (
                    <RequestItem key={entry.id} entry={entry} now={now} selected={entry.id === selectedId} onClick={() => handleRequestClick(entry)} />
                  ))}
                </ul>
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function TabBtn({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`py-3.5 text-sm font-bold flex items-center justify-center gap-1.5 border-b-3 ${active ? "border-sea text-ink" : "border-transparent text-ink-soft hover:text-ink"}`}
    >
      {icon}
      {label}
    </button>
  );
}

function RequestItem({ entry, now, selected, onClick }: { entry: AdvisoryLogEntry; now: Date; selected: boolean; onClick: () => void }) {
  const state = logState(entry.risk_class);
  return (
    <li>
      <button onClick={onClick} className={`w-full text-left px-4 py-3 border-b border-rule flex gap-3 items-center ${selected ? "bg-mist" : "hover:bg-mist"}`}>
        <div className={`${SIGN_THEME[state].bg} rounded-lg p-1 shrink-0`}>
          <VerdictSign state={state} size={26} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-bold text-ink">
            {displayStatus(entry.risk_class) === "NO-GO" ? "No-go" : displayStatus(entry.risk_class).charAt(0) + displayStatus(entry.risk_class).slice(1).toLowerCase()}
            <span className="font-normal text-ink-soft">, {entry.boat_class.replace(/_/g, " ")}</span>
          </p>
          <p className="text-sm text-ink-soft tabular-nums">
            {entry.lat.toFixed(3)}° N, {entry.lon.toFixed(3)}° E, asked {ageLabel(new Date(entry.issued_at), now)}
          </p>
          {entry.valid_for && <p className="text-xs font-semibold text-sea">For leaving {utcStamp(entry.valid_for)}</p>}
        </div>
      </button>
    </li>
  );
}

function Health({ label, load, count }: { label: string; load: Load<unknown>; count?: number }) {
  if (load.state === "loading") {
    return <span className="px-2.5 py-1.5 rounded-lg bg-white/10 flex items-center gap-1.5"><Loader2 className="w-3.5 h-3.5 animate-spin" />{label}</span>;
  }
  if (load.state === "error") {
    return (
      <span role="alert" title={load.message} className="px-2.5 py-1.5 rounded-lg bg-danger font-semibold flex items-center gap-1.5">
        <AlertTriangle className="w-3.5 h-3.5" />{label} down
      </span>
    );
  }
  return (
    <span className="px-2.5 py-1.5 rounded-lg bg-white/10 flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full bg-[#3ecf8e]" />{label}{count !== undefined && ` ${count}`}
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
      className={`px-3 py-2 rounded-lg shadow text-sm font-semibold ${
        disabled ? "bg-ink/60 text-white/40 cursor-not-allowed line-through" :
        active ? "bg-white text-ink" : "bg-ink/85 text-white hover:bg-ink"
      }`}
    >
      {label}
    </button>
  );
}

function RasterLegend({ layer, error }: { layer: RasterLayer; error?: string }) {
  const style = RASTER_STYLE[layer.layer];
  return (
    <div className="bg-ink/90 text-white text-xs rounded-lg px-3 py-2.5 w-72 space-y-1.5">
      {error ? (
        <p className="text-red-300 font-semibold">Tiles failed to load: {error}</p>
      ) : (
        <>
          <div className="h-2.5 rounded" style={{ background: style.gradient }} />
          <div className="flex justify-between tabular-nums"><span>{style.rescale[0]}</span><span>{layer.unit || "colour scale"}</span><span>{style.rescale[1]}</span></div>
        </>
      )}
      <p className="text-white/75">
        {sourceName(layer.dataset_id)}, {layer.variable}. Valid {utcStamp(layer.valid_time)}.
      </p>
    </div>
  );
}

function PfzDetails({ props }: { props: Record<string, unknown> }) {
  const text = (key: string) => (props[key] == null || props[key] === "" ? null : String(props[key]));
  const url = text("source_url");
  const issued = text("issued_for");
  return (
    <div className="text-sm text-ink space-y-0.5">
      <p className="font-bold">Potential fishing zone</p>
      {issued && <p>INCOIS advisory of {new Date(issued).toLocaleDateString("en-IN", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" })}</p>}
      {text("basis") && <p>Based on {text("basis")}</p>}
      {text("state_name") && <p>Sector: {text("state_name")}</p>}
      <p className="text-ink-soft pt-1">
        {text("source_name") ?? "INCOIS PFZ advisory"}, fetched {utcStamp(text("fetched_at"))}.{" "}
        {url && <a href={url} target="_blank" rel="noreferrer" className="text-sea underline">Source</a>}
      </p>
    </div>
  );
}
