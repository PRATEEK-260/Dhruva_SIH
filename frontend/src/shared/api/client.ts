// Thin fetch wrappers over the backend's /advisory and /geo routes. The /api
// prefix matches both the Vite dev proxy (vite.config.ts) and deploy/Caddyfile's
// existing strip-prefix convention, so this code is unchanged between dev and
// a Caddy-fronted deployment.
//
// FeatureCollection comes from the `geojson` package's own types (react-map-gl
// and maplibre-gl both depend on it already, so it resolves without a new
// dependency) rather than a hand-rolled interface — react-map-gl's <Source
// data={...}> prop expects exactly this type, so using it directly here means
// ShoreApp.tsx never needs to cast past the type checker to pass a fetched
// layer straight into <Source>.
import type { FeatureCollection } from "geojson";

export interface AdvisoryRequest {
  query: string;
  lat: number;
  lon: number;
  language?: string;
  boat_class?: string;
  when?: string;
  log?: boolean;
  /** TEST INPUT: simulates a cyclone warning this far away. */
  test_cyclone_km?: number;
  /** A stored past IMD bulletin; the cyclone distance comes from its centre. */
  bulletin?: string;
}

export interface EvidenceItem {
  key: string;
  value: number;
  unit: string;
  dataset_id: string;
  upstream_dataset_id?: string | null;
  cell: string;
  offset_km?: number | null;
  valid_time?: string | null;
  is_forecast: boolean;
  threshold?: number | null;
  rule_id?: string | null;
}

export interface EvidenceBundle {
  items: EvidenceItem[];
  risk_class: string | null;
  fired_rules: string[];
  provisional_thresholds: boolean;
  notice: string;
  built_at: string;
}

export interface RasterLayer {
  layer: string;
  file: string;
  dataset_id: string;
  variable: string;
  unit: string;
  valid_time: string | null;
  generated_at: string;
}

/** One of the problem statement's nine agents, as it ran for one question. */
export interface TraceStep {
  agent: string;
  node: string;
  ran: boolean;
  line: string;
}

/** Nearest line of the latest fresh INCOIS PFZ advisory (backend dhruva/geo/pfz.py). */
export interface NearestPfz {
  uid: string;
  issued_for: string;
  category: string | null;
  basis: string | null;
  state_name: string | null;
  distance_nm: number;
  bearing_deg: number;
  lat: number;
  lon: number;
  age_days: number;
  confidence: number;
  source_url: string;
  fetched_at: string;
  centre_name: string | null;
  centre_distance_nm: number | null;
  centre_bearing_deg: number | null;
}

export interface AdvisoryResponse {
  narration: string;
  risk_class: string;
  firewall_passed: boolean;
  evidence: Record<string, unknown>;
  capsule_base32: string;
  reason_code: number;
  notice: string;
  intent?: string;
  fired_rules?: string[];
  hazard_flags?: string[];
  trace?: TraceStep[];
  view?: { cards?: string[]; layers?: string[] };
  pfz?: NearestPfz | null;
  /** Set only when this answer is a recorded real run, replayed. */
  recorded_at?: string | null;
  replay_reason?: string | null;
}

/** A named position used by the shore console's Warn boats view. Not a vessel. */
export interface DemoBoat {
  name: string;
  lat: number;
  lon: number;
  demo: true;
  boat_class: string;
}

export async function fetchDemoBoats(): Promise<DemoBoat[]> {
  const response = await fetch("/api/demo/boats");
  return parseOrThrow<DemoBoat[]>(response, "fetchDemoBoats");
}

export interface AdvisoryLogEntry {
  id: number;
  boat_class: string;
  lat: number;
  lon: number;
  risk_class: string;
  issued_at: string;
  /** Set when the verdict was computed for a past instant, not issued_at. */
  valid_for: string | null;
}

export type GeoFeatureCollection = FeatureCollection;

async function parseOrThrow<T>(response: Response, what: string): Promise<T> {
  if (!response.ok) {
    throw new Error(`${what} failed: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function postAdvisory(req: AdvisoryRequest): Promise<AdvisoryResponse> {
  const response = await fetch("/api/advisory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return parseOrThrow<AdvisoryResponse>(response, "postAdvisory");
}

export async function fetchRecentAdvisories(limit = 20): Promise<AdvisoryLogEntry[]> {
  const response = await fetch(`/api/advisory/recent?limit=${limit}`);
  return parseOrThrow<AdvisoryLogEntry[]>(response, "fetchRecentAdvisories");
}

export async function fetchGeoLayer(
  name: "boundaries" | "zones" | "pfz",
): Promise<GeoFeatureCollection> {
  const response = await fetch(`/api/geo/${name}`);
  return parseOrThrow<GeoFeatureCollection>(response, `fetchGeoLayer(${name})`);
}

export async function fetchRasterLayers(): Promise<RasterLayer[]> {
  const response = await fetch("/api/geo/rasters");
  return parseOrThrow<RasterLayer[]>(response, "fetchRasterLayers");
}

export async function fetchHealth(): Promise<{ status: string }> {
  const response = await fetch("/api/health");
  return parseOrThrow<{ status: string }>(response, "fetchHealth");
}
