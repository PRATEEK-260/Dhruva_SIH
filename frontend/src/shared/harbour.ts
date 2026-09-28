// Distance and direction to the nearest pilot harbour, worked out on the phone
// from the position the capsule carries. Pure arithmetic and a shipped list, so it
// works with the radio off.
//
// Positions from OpenStreetMap (Nominatim, looked up 28 Sep 2026).

import { compassWord, type Language } from "./capsule/codebook";

export interface Harbour {
  name: string;
  lat: number;
  lon: number;
}

export const HARBOURS: Harbour[] = [
  { name: "Karaikal Port", lat: 10.8388, lon: 79.8457 },
  { name: "Nagapattinam Harbour", lat: 10.7599, lon: 79.8499 },
];

const EARTH_KM = 6371.0088;
const rad = (d: number) => (d * Math.PI) / 180;

export function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = rad(lat2 - lat1);
  const dLon = rad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.sqrt(a));
}

/** Initial great-circle bearing, degrees clockwise from north. */
export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const y = Math.sin(rad(lon2 - lon1)) * Math.cos(rad(lat2));
  const x =
    Math.cos(rad(lat1)) * Math.sin(rad(lat2)) -
    Math.sin(rad(lat1)) * Math.cos(rad(lat2)) * Math.cos(rad(lon2 - lon1));
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/** The point `km` away along `bearing` (degrees) on a sphere. */
export function destination(lat: number, lon: number, bearing: number, km: number): [lat: number, lon: number] {
  const d = km / EARTH_KM;
  const b = rad(bearing);
  const la = rad(lat);
  const lat2 = Math.asin(Math.sin(la) * Math.cos(d) + Math.cos(la) * Math.sin(d) * Math.cos(b));
  const lon2 = rad(lon) + Math.atan2(Math.sin(b) * Math.sin(d) * Math.cos(la), Math.cos(d) - Math.sin(la) * Math.sin(lat2));
  return [(lat2 * 180) / Math.PI, (((lon2 * 180) / Math.PI + 540) % 360) - 180];
}

/** A geodesic circle as a closed GeoJSON ring, [lon, lat] order. */
export function circleRing(lat: number, lon: number, km: number, steps = 96): [number, number][] {
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const [la, lo] = destination(lat, lon, (i * 360) / steps, km);
    ring.push([lo, la]);
  }
  return ring;
}

export interface WayHome {
  harbour: Harbour;
  km: number;
  bearing: number;
  direction: string;
}

export function wayHome(lat: number, lon: number, lang: Language): WayHome {
  const ranked = HARBOURS.map((h) => ({ h, km: distanceKm(lat, lon, h.lat, h.lon) })).sort(
    (a, b) => a.km - b.km,
  );
  const { h, km } = ranked[0];
  const bearing = bearingDeg(lat, lon, h.lat, h.lon);
  return { harbour: h, km, bearing, direction: compassWord(bearing, lang) };
}
