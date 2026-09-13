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
}

export interface AdvisoryResponse {
  narration: string;
  risk_class: string;
  firewall_passed: boolean;
  evidence: Record<string, unknown>;
  capsule_base32: string;
  reason_code: number;
  notice: string;
}

export interface AdvisoryLogEntry {
  id: number;
  boat_class: string;
  lat: number;
  lon: number;
  risk_class: string;
  issued_at: string;
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
