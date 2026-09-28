import { useEffect, useMemo, useState } from "react";
import Map, { Layer, Marker, Source } from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";
import "../shared/map/maplibre";
import type { FeatureCollection } from "geojson";
import { fetchGeoLayer, type NearestPfz } from "../shared/api/client";
import { BASEMAPS } from "../shared/map/basemaps";
import { PFZ_CASING, PFZ_YELLOW } from "../shared/map/colours";

/** The boat, today's INCOIS fishing-zone lines, and a dashed line to the nearest
 * one. Online only: map tiles need a network, and at sea the card's distance
 * and direction carry the same answer without them. */
export function PfzMap({ lat, lon, pfz }: { lat: number; lon: number; pfz: NearestPfz }) {
  const [lines, setLines] = useState<FeatureCollection | null>(null);

  useEffect(() => {
    let live = true;
    fetchGeoLayer("pfz")
      .then((fc) => live && setLines(fc))
      .catch(() => live && setLines(null));
    return () => {
      live = false;
    };
  }, []);

  const connector = useMemo<FeatureCollection>(
    () => ({
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: [[lon, lat], [pfz.lon, pfz.lat]] },
        },
      ],
    }),
    [lat, lon, pfz.lat, pfz.lon],
  );

  // Frame the boat and the nearest point with room around both.
  const pad = 0.12;
  const bounds: [[number, number], [number, number]] = [
    [Math.min(lon, pfz.lon) - pad, Math.min(lat, pfz.lat) - pad],
    [Math.max(lon, pfz.lon) + pad, Math.max(lat, pfz.lat) + pad],
  ];

  return (
    <div className="mt-3 h-52 rounded-xl overflow-hidden border border-rule relative">
      <Map
        initialViewState={{ bounds, fitBoundsOptions: { padding: 28 } }}
        mapStyle={BASEMAPS.seafloor.style}
        style={{ width: "100%", height: "100%" }}
        attributionControl={false}
        dragRotate={false}
        touchPitch={false}
      >
        {lines && (
          <Source id="pfz" type="geojson" data={lines}>
            <Layer id="pfz-casing" type="line" paint={{ "line-color": PFZ_CASING, "line-width": 6 }} />
            <Layer id="pfz-line" type="line" paint={{ "line-color": PFZ_YELLOW, "line-width": 3 }} />
          </Source>
        )}
        <Source id="to-pfz" type="geojson" data={connector}>
          <Layer id="to-pfz-line" type="line" paint={{ "line-color": "#0f2a36", "line-width": 2.5, "line-dasharray": [2, 1.5] }} />
        </Source>
        <Marker longitude={pfz.lon} latitude={pfz.lat} anchor="center">
          <div className="w-4 h-4 rounded-full border-[3px] border-ink shadow" style={{ background: PFZ_YELLOW }} />
        </Marker>
        <Marker longitude={lon} latitude={lat} anchor="center">
          <div className="px-2 py-1 rounded-lg bg-ink text-white text-xs font-bold shadow">You</div>
        </Marker>
      </Map>
      <p className="absolute top-2 left-2 bg-white/90 text-ink text-xs font-semibold px-2 py-1 rounded-md">
        Yellow lines: INCOIS potential fishing zones
      </p>
      {/* The base map's credit, kept to one line so it does not cover the map. */}
      <p className="absolute bottom-1 right-1 bg-white/85 text-ink-soft text-[10px] px-1.5 py-0.5 rounded">
        Esri, GEBCO, NOAA, Garmin, HERE
      </p>
    </div>
  );
}
